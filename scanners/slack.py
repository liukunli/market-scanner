"""Slack posting + channel routing.

Token resolution: SLACK_BOT_TOKEN env var wins; otherwise falls back to the
committed config.SLACK_BOT_TOKEN. Routing sends each symbol to its
highest-priority focus tier: index ETF > QQQ > S&P 500 > other.
"""
from __future__ import annotations

import json
import os
import urllib.request
import urllib.parse
import uuid
from typing import Iterable, Optional

from .config import CHANNELS, INDEX_ETFS
from . import config as _config


def _resolve_token(token: Optional[str]) -> Optional[str]:
    """Env var wins; fall back to the committed config token."""
    return token or os.environ.get("SLACK_BOT_TOKEN") or getattr(_config, "SLACK_BOT_TOKEN", None)


def route_channel(symbol: str, qqq: Iterable[str], sp500: Iterable[str]) -> str:
    """Return the channel ID a symbol's signal should post to."""
    if symbol in INDEX_ETFS:
        return CHANNELS["index_options"]
    if symbol in set(qqq):
        return CHANNELS["qqq"]
    if symbol in set(sp500):
        return CHANNELS["sp500"]
    return CHANNELS["other_5b"]


def post(channel_id: str, text: str, token: Optional[str] = None) -> dict:
    """Post a message via chat.postMessage. Returns the parsed API response.

    Raises RuntimeError if Slack's response has "ok": false (e.g. not_in_channel,
    channel_not_found, missing_scope) - these come back as HTTP 200, so a plain
    network try/except around this call would otherwise never see the failure.
    """
    token = _resolve_token(token)
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN not set")
    payload = json.dumps({"channel": channel_id, "text": text}).encode()
    req = urllib.request.Request(
        "https://slack.com/api/chat.postMessage", data=payload,
        headers={"Content-Type": "application/json; charset=utf-8",
                 "Authorization": f"Bearer {token}"}, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:
        result = json.loads(resp.read().decode())
    if not result.get("ok"):
        raise RuntimeError(f"Slack post to {channel_id} failed: {result.get('error')}")
    return result


def upload_image(channel_id: str, image_path: str, comment: str,
                 token: Optional[str] = None) -> dict:
    """Upload a PNG to a channel via Slack's 3-step external-upload flow."""
    token = _resolve_token(token)
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN not set")
    auth = {"Authorization": f"Bearer {token}"}
    with open(image_path, "rb") as fh:
        data = fh.read()
    name = os.path.basename(image_path)

    # 1) reserve an upload URL
    p = urllib.parse.urlencode({"filename": name, "length": len(data)}).encode()
    r = json.loads(urllib.request.urlopen(urllib.request.Request(
        "https://slack.com/api/files.getUploadURLExternal", data=p,
        headers={**auth, "Content-Type": "application/x-www-form-urlencoded"},
        method="POST"), timeout=20).read())
    if not r.get("ok"):
        raise RuntimeError(f"getUploadURL failed: {r.get('error')}")
    upload_url, file_id = r["upload_url"], r["file_id"]

    # 2) POST the bytes (multipart)
    b = "----bt" + uuid.uuid4().hex
    body = (f'--{b}\r\nContent-Disposition: form-data; name="file"; '
            f'filename="{name}"\r\nContent-Type: image/png\r\n\r\n').encode() \
        + data + f"\r\n--{b}--\r\n".encode()
    urllib.request.urlopen(urllib.request.Request(
        upload_url, data=body,
        headers={"Content-Type": f"multipart/form-data; boundary={b}"},
        method="POST"), timeout=40).read()

    # 3) complete -> shares into the channel with the caption
    comp = json.dumps({"files": [{"id": file_id, "title": name}],
                      "channel_id": channel_id, "initial_comment": comment}).encode()
    result = json.loads(urllib.request.urlopen(urllib.request.Request(
        "https://slack.com/api/files.completeUploadExternal", data=comp,
        headers={**auth, "Content-Type": "application/json; charset=utf-8"},
        method="POST"), timeout=20).read())
    if not result.get("ok"):
        raise RuntimeError(f"completeUploadExternal to {channel_id} failed: {result.get('error')}")
    return result


def post_signal(channel_id: str, text: str, chart_path: Optional[str] = None,
                token: Optional[str] = None) -> dict:
    """Post a signal with its chart if available, else fall back to text."""
    if chart_path and os.path.exists(chart_path):
        try:
            return upload_image(channel_id, chart_path, text, token)
        except Exception:
            pass  # network / matplotlib / scope issue -> degrade to text
    return post(channel_id, text, token)
