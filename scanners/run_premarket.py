"""Entrypoint: pre-market gap scan over QQQ (Nasdaq-100) and S&P 500 constituents.

Invoked by the Claude scheduled task ~9:00 AM ET on trading days:
    python3 -m scanners.run_premarket

No longer posts to Slack. It prints a plain-text report (and writes it to
premarket_report.txt) that the scheduled task delivers by email.
"""
from __future__ import annotations

import time
from pathlib import Path

from . import universe, yahoo
from .config import PREMARKET
from .format import format_premarket
from .premarket import Quote, scan
from .timeutil import today_local

REPORT_PATH = Path("premarket_report.txt")

UNIVERSES = [("QQQ", universe.qqq_constituents),
             ("S&P 500", universe.sp500_constituents)]


def _plain(text: str) -> str:
    """Strip Slack markdown (*bold*, _italic_) so the text reads cleanly in email."""
    return text.replace("*", "").replace("_", "")


def run() -> dict:
    now = time.time()
    today = today_local(now)
    session = yahoo.latest_session_date()
    if session != today:
        print(f"[skip] no live session today (latest={session}, today={today})")
        return {"skipped": True, "latest_session": session, "report": None}

    members, fetch_errors = {}, {}
    for label, fetch_fn in UNIVERSES:
        try:
            members[label] = set(fetch_fn(now))
        except universe.UniverseFetchError as e:
            print(f"[error] {label} universe fetch failed: {e}")
            fetch_errors[label] = str(e)

    # fetch every unique symbol ONCE, then slice per universe
    all_syms = list(dict.fromkeys(s for ms in members.values() for s in ms))
    raw = yahoo.fetch_all(all_syms, yahoo.premarket_quote)
    quotes = {s: Quote(symbol=s, prev_close=r[0], premarket_price=r[1],
                      premarket_volume=r[2])
              for s, r in raw.items() if r}

    summary, sections = {}, []
    for label, _fetch_fn in UNIVERSES:
        if label in fetch_errors:
            summary[label] = {"fetch_error": fetch_errors[label]}
            sections.append(f"Pre-Market Gap Scanner — {label}\n"
                            f"!! Could not load the {label} constituent list: "
                            f"{fetch_errors[label]}")
            continue
        qs = [quotes[s] for s in members[label] if s in quotes]
        ups, downs = scan(qs, PREMARKET)
        summary[label] = {"ups": len(ups), "downs": len(downs), "quoted": len(qs)}
        sections.append(_plain(format_premarket(label, ups, downs)))

    report = f"Pre-market gappers — {today}\n\n" + "\n\n".join(sections)
    REPORT_PATH.write_text(report)
    summary["report"] = report
    return summary


if __name__ == "__main__":
    result = run()
    print(result.get("report") or result)
