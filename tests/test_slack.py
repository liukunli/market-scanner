"""Tests for Slack posting failure surfacing (ok: false -> raise, not silent)."""
import json

import pytest

from scanners import slack


class _FakeResponse:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode()

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_post_raises_on_ok_false(monkeypatch):
    monkeypatch.setattr(slack.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse({"ok": False, "error": "not_in_channel"}))
    with pytest.raises(RuntimeError, match="not_in_channel"):
        slack.post("C123", "hello", token="xoxb-fake")


def test_post_returns_result_on_ok_true(monkeypatch):
    monkeypatch.setattr(slack.urllib.request, "urlopen",
                        lambda *a, **k: _FakeResponse({"ok": True, "ts": "123.456"}))
    result = slack.post("C123", "hello", token="xoxb-fake")
    assert result["ok"] is True


def test_post_signal_propagates_text_post_failure(monkeypatch):
    # no chart_path -> post_signal goes straight to post(), which must surface
    # a real ok:false failure rather than swallowing it silently.
    def fake_post(*a, **k):
        raise RuntimeError("Slack post to C123 failed: not_in_channel")

    monkeypatch.setattr(slack, "post", fake_post)
    with pytest.raises(RuntimeError, match="not_in_channel"):
        slack.post_signal("C123", "hello", chart_path=None)


def test_post_signal_falls_back_when_chart_upload_fails(monkeypatch, tmp_path):
    # chart upload fails for a chart-specific reason (e.g. bad image) -> must
    # still degrade to a successful text post rather than propagating.
    chart = tmp_path / "chart.png"
    chart.write_bytes(b"not a real png")

    def fake_upload_image(*a, **k):
        raise RuntimeError("upload failed: some transient issue")

    calls = {}
    monkeypatch.setattr(slack, "upload_image", fake_upload_image)
    monkeypatch.setattr(slack, "post", lambda ch, text, token=None: calls.setdefault("t", (ch, text)))
    slack.post_signal("C123", "hello", chart_path=str(chart))
    assert calls["t"] == ("C123", "hello")
