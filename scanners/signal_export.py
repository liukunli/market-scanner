"""Export each hourly signal to a self-describing JSON record.

Each record carries everything a viewer needs to render and explain the signal:
the OHLCV bars around it (tagged by role), the six gate evaluations, the trade
levels, and the realized outcome. No plotting here — see visualize.py.

CLI:
    python3 -m scanners.signal_export AAPL NVDA GATX --day 2026-07-02 --out signals.json
    python3 -m scanners.signal_export --day 2026-07-02 --out signals.json      # default: index ETFs
"""
from __future__ import annotations

import argparse
import json
import statistics
from typing import Optional, Sequence

from . import yahoo
from .backtest import simulate
from .config import HourlyConfig, HOURLY, INDEX_ETFS
from .hourly import Bar, evaluate
from .timeutil import local_date, to_local


def _iso(ts: int) -> str:
    return to_local(ts).strftime("%Y-%m-%d %H:%M")


def _gates(p: Bar, c: Bar, bars: Sequence[Bar], i: int, side: str,
           cfg: HourlyConfig) -> tuple[dict, float]:
    """Return (gate report, relative volume) mirroring hourly.evaluate."""
    base = bars[i - 1 - cfg.vol_lookback:i - 1]
    base_vol = statistics.fmean(b.volume for b in base) if base else 0.0
    rvol = (statistics.fmean((p.volume, c.volume)) / base_vol) if base_vol > 0 else 0.0

    if side == "up":
        g_p, g_c = p.close - p.open, c.close - c.open
        trending = g_p > 0 and g_c > 0 and c.close > p.close
        near_lhs, near_rhs = c.low, p.high - cfg.low_near_high_frac * p.range
        near = near_lhs >= near_rhs
        drawback = (p.close - c.low) / p.range
    else:
        g_p, g_c = p.open - p.close, c.open - c.close
        trending = g_p > 0 and g_c > 0 and c.close < p.close
        near_lhs, near_rhs = c.high, p.low + cfg.low_near_high_frac * p.range
        near = near_lhs <= near_rhs
        drawback = (c.high - p.close) / p.range
    mag = abs(g_c - g_p) / max(abs(g_p), abs(g_c)) if max(abs(g_p), abs(g_c)) > 0 else 1.0

    gates = {
        "relative_volume": {"value": round(rvol, 3), "threshold": cfg.rvol_min,
                            "baseline_avg_volume": round(base_vol, 1),
                            "pass": rvol >= cfg.rvol_min},
        "continuous_growth": {"prev_gain": round(g_p, 4), "curr_gain": round(g_c, 4),
                             "pass": bool(trending)},
        "low_near_prev_high": {"value": round(near_lhs, 4), "bound": round(near_rhs, 4),
                              "pass": bool(near)},
        "minimal_drawback": {"value": round(drawback, 4), "threshold": cfg.max_drawback_frac,
                            "pass": drawback <= cfg.max_drawback_frac},
        "same_magnitude": {"value": round(mag, 4), "threshold": cfg.magnitude_tol,
                          "pass": mag <= cfg.magnitude_tol},
    }
    return gates, rvol


def _outcome(bars: Sequence[Bar], i: int, side: str, entry: float, stop: float,
             target: float, breakeven_trigger: float, horizon: int) -> dict:
    result, px, armed = simulate(bars, i, side, entry, stop, target,
                                 breakeven_trigger, horizon)
    r = (px - entry) if side == "up" else (entry - px)
    return {"result": result, "exit_price": round(px, 4),
            "breakeven_armed": armed,
            "r_multiple": round(r / abs(entry - stop), 3) if entry != stop else 0.0}


def _bar_window(bars: Sequence[Bar], i: int, context: int, forward_show: int) -> list[dict]:
    lo, hi = max(0, i - 1 - context), min(len(bars), i + 1 + forward_show)
    out = []
    for j in range(lo, hi):
        role = ("prev" if j == i - 1 else "curr" if j == i else
                "forward" if j > i else "context")
        b = bars[j]
        out.append({"time": _iso(b.ts), "open": b.open, "high": b.high,
                   "low": b.low, "close": b.close, "volume": b.volume, "role": role})
    return out


def build_record(symbol: str, bars: Sequence[Bar], i: int, side: str,
                 cfg: HourlyConfig, context: int, forward_show: int) -> Optional[dict]:
    sig = evaluate(symbol, bars[:i + 1], side, cfg)
    if not sig:
        return None
    p, c = bars[i - 1], bars[i]
    gates, _ = _gates(p, c, bars, i, side, cfg)
    gbar = ((c.close - c.open) + (p.close - p.open)) / 2 if side == "up" \
        else ((p.open - p.close) + (c.open - c.close)) / 2
    outcome = _outcome(bars, i, side, sig.entry, sig.stop_loss, sig.take_profit,
                       sig.breakeven_trigger, cfg.tp_bars)
    return {
        "symbol": symbol, "side": side, "signal_time": _iso(sig.bar_ts),
        "gates": gates,
        "levels": {"entry": sig.entry, "stop": sig.stop_loss, "target": sig.take_profit,
                  "breakeven_trigger": sig.breakeven_trigger,
                  "risk": round(abs(sig.entry - sig.stop_loss), 4),
                  "reward": round(abs(sig.take_profit - sig.entry), 4),
                  "risk_reward": sig.risk_reward, "rvol": sig.rvol, "gbar": round(gbar, 4)},
        "outcome": outcome,
        "bars": _bar_window(bars, i, context, forward_show),
    }


def export(symbols, day: str, cfg: HourlyConfig = HOURLY,
           context: int = 10, forward_show: int = 4) -> dict:
    bars_by = yahoo.fetch_all(symbols, lambda s: yahoo.hourly_bars(s, "1mo"))
    records = []
    for sym, bars in bars_by.items():
        if not bars or len(bars) < cfg.min_bars:
            continue
        for i in range(cfg.min_bars - 1, len(bars)):
            if local_date(bars[i].ts) != day:
                continue
            for side in ("up", "down"):
                rec = build_record(sym, bars, i, side, cfg, context, forward_show)
                if rec:
                    records.append(rec)
    return {"day": day,
            "config": {"rvol_min": cfg.rvol_min, "tp_bars": cfg.tp_bars,
                      "low_near_high_frac": cfg.low_near_high_frac,
                      "max_drawback_frac": cfg.max_drawback_frac,
                      "magnitude_tol": cfg.magnitude_tol},
            "count": len(records), "signals": records}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("symbols", nargs="*", help="tickers (default: index ETFs)")
    ap.add_argument("--day", required=True, help="YYYY-MM-DD trading day to scan")
    ap.add_argument("--out", default="signals.json")
    args = ap.parse_args()
    symbols = args.symbols or list(INDEX_ETFS)
    data = export(symbols, args.day)
    with open(args.out, "w") as fh:
        json.dump(data, fh, indent=2)
    print(f"Wrote {data['count']} signal(s) for {args.day} -> {args.out}")


if __name__ == "__main__":
    main()
