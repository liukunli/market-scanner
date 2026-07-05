"""Slack posting + channel routing.

Reads the bot token from SLACK_BOT_TOKEN (never hard-coded). Routing sends each
symbol to its highest-priority focus tier: index ETF > QQQ > S&P 500 > other.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Iterable, Optional

from .config import CHANNELS, INDEX_ETFS


def route_channel(symbol: str, qqq: Iterable[str], sp500: Iterable[str]) -> str:
    """Return the channel ID a symbol's signal should post to."""
    if symbol in INDEX_ETFS:
        return CHANNELS["index_etf"]
    if symbol in set(qqq):
        return CHANNELS["qqq"]
    if symbol in set(sp500):
        return CHANNELS["sp500"]
    return CHANNELS["other_5b"]


def post(channel_id: str, text: str, token: Optional[str] = None) -> dict:
    """Post a message via chat.postMessage. Returns the parsed API response."""
    token = token or os.environ.get("SLACK_BOT_TOKEN")
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN not set")
    payload = json.dumps({"channel": channel_id, "text": text}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage", data=payload,
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Authorization": f"Bearer {token}"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.loads(resp.read().decode())
