"""Render signal JSON (from signal_export) into candlestick charts.

One PNG per signal: OHLC candles for the context/setup/forward window, the two
trigger bars highlighted, and entry / stop / target as reference lines
distinguished by line-STYLE and labels (not color alone, so it stays readable
under color-vision deficiency and in print). An index.html links them all.

CLI:
    python3 -m scanners.visualize signals.json --outdir charts
"""
from __future__ import annotations

import argparse
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

# Semantic price colors (up = gain, down = loss) — the only place hue is meaningful.
UP, DOWN = "#1a9850", "#d73027"          # CVD-safe green / red
SETUP_BAND = "#fff3bf"                    # soft highlight behind the two trigger bars
INK, MUTED, GRID = "#1b1f24", "#6b7280", "#e5e7eb"
ENTRY_C, STOP_C, TARGET_C, BE_C = "#2166ac", "#d73027", "#1a9850", "#f39c12"


def _draw_candles(ax, bars):
    for x, b in enumerate(bars):
        up = b["close"] >= b["open"]
        color = UP if up else DOWN
        # wick
        ax.plot([x, x], [b["low"], b["high"]], color=color, lw=1.2, zorder=2)
        # body (min height so dojis are visible)
        lo, hi = min(b["open"], b["close"]), max(b["open"], b["close"])
        h = max(hi - lo, (bars[0]["high"] - bars[0]["low"]) * 0.002)
        ax.add_patch(Rectangle((x - 0.3, lo), 0.6, h, facecolor=color,
                              edgecolor=color, linewidth=0.5, zorder=3))


def render_signal(sig, path):
    bars = sig["bars"]
    lv = sig["levels"]
    fig, ax = plt.subplots(figsize=(11, 6))

    # highlight the two trigger bars (prev + curr)
    idx = {b["role"]: i for i, b in enumerate(bars)}
    if "prev" in idx and "curr" in idx:
        ax.axvspan(idx["prev"] - 0.45, idx["curr"] + 0.45, color=SETUP_BAND, zorder=0)

    _draw_candles(ax, bars)

    # reference lines: solid entry, dashed stop, dotted target (style-coded)
    ax.axhline(lv["entry"], color=ENTRY_C, lw=2, ls="-", zorder=4,
               label=f"Entry {lv['entry']:.2f}")
    ax.axhline(lv["stop"], color=STOP_C, lw=1.8, ls="--", zorder=4,
               label=f"Stop {lv['stop']:.2f}")
    ax.axhline(lv["target"], color=TARGET_C, lw=1.8, ls=":", zorder=4,
               label=f"Target {lv['target']:.2f}")
    if lv.get("breakeven_trigger"):
        ax.axhline(lv["breakeven_trigger"], color=BE_C, lw=1.5, ls="-.", zorder=4,
                   label=f"BE trigger {lv['breakeven_trigger']:.2f} → stop to entry")

    # x labels = bar times (HH:MM), rotated
    ax.set_xticks(range(len(bars)))
    ax.set_xticklabels([b["time"][-5:] for b in bars], rotation=45, ha="right",
                       fontsize=8, color=MUTED)
    ax.set_xlim(-0.7, len(bars) - 0.3)

    oc = sig["outcome"]
    badge = {"target": "✓ TARGET", "stop": "✗ STOP",
             "breakeven": "= BREAKEVEN", "open": "• OPEN"}[oc["result"]]
    side = "BUY" if sig["side"] == "up" else "SHORT"
    ax.set_title(f"{sig['symbol']}  {side}  @ {sig['signal_time']}   "
                 f"{badge}  ({oc['r_multiple']:+.2f}R)",
                 fontsize=13, color=INK, fontweight="bold", loc="left")

    # gate summary box
    gtxt = "\n".join(
        f"{'✓' if g.get('pass') else '✗'} {name.replace('_',' ')}"
        for name, g in sig["gates"].items())
    gtxt += (f"\n———\nR:R {lv['risk_reward']:.2f}   rvol {lv['rvol']:.2f}"
             f"\nrisk {lv['risk']:.2f}  reward {lv['reward']:.2f}")
    ax.text(1.012, 0.5, gtxt, transform=ax.transAxes, va="center", ha="left",
            fontsize=8.5, family="monospace", color=INK,
            bbox=dict(boxstyle="round,pad=0.5", fc="#f8fafc", ec=GRID))

    ax.grid(axis="y", color=GRID, lw=0.7, zorder=1)
    ax.set_axisbelow(True)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    for s in ("left", "bottom"):
        ax.spines[s].set_color(GRID)
    ax.tick_params(colors=MUTED)
    ax.legend(loc="upper left", fontsize=8, framealpha=0.9, edgecolor=GRID)
    ax.set_ylabel("Price", color=MUTED, fontsize=9)
    fig.subplots_adjust(right=0.8)
    fig.savefig(path, dpi=130, bbox_inches="tight")
    plt.close(fig)


def render_all(data, outdir):
    os.makedirs(outdir, exist_ok=True)
    items = []
    for k, sig in enumerate(data["signals"]):
        fname = f"{k:03d}_{sig['symbol']}_{sig['side']}.png"
        render_signal(sig, os.path.join(outdir, fname))
        items.append((fname, sig))
    # index.html
    rows = "\n".join(
        f'<figure><img src="{f}" style="width:100%"><figcaption>'
        f'{s["symbol"]} {s["side"]} — {s["outcome"]["result"]} '
        f'({s["outcome"]["r_multiple"]:+.2f}R)</figcaption></figure>'
        for f, s in items)
    html = (f"<!doctype html><meta charset=utf-8><title>Signals {data['day']}</title>"
            f"<body style='font-family:system-ui;max-width:1100px;margin:2rem auto'>"
            f"<h1>Signals — {data['day']} ({data['count']})</h1>{rows}</body>")
    with open(os.path.join(outdir, "index.html"), "w") as fh:
        fh.write(html)
    return len(items)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("json_file")
    ap.add_argument("--outdir", default="charts")
    args = ap.parse_args()
    with open(args.json_file) as fh:
        data = json.load(fh)
    n = render_all(data, args.outdir)
    print(f"Rendered {n} chart(s) -> {args.outdir}/ (open {args.outdir}/index.html)")


if __name__ == "__main__":
    main()
