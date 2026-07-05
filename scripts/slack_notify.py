#!/usr/bin/env python3
"""Send a message to Slack via Incoming Webhook or Bot token.

Credentials are read from the environment (or a local .env file), never hardcoded:

  Option A — Incoming Webhook (simplest):
      export SLACK_WEBHOOK_URL="https://hooks.slack.com/services/XXX/YYY/ZZZ"

  Option B — Bot token + channel (richer, multi-channel):
      export SLACK_BOT_TOKEN="xoxb-..."
      export SLACK_CHANNEL="#general"     # or a channel ID like C0123456

Usage:
      python scripts/slack_notify.py "Hello from Claude Code"
      echo "piped message" | python scripts/slack_notify.py
      python scripts/slack_notify.py --channel "#alerts" "override channel (bot token only)"

Exit code 0 on success, non-zero on failure.
"""
import json
import os
import sys
import urllib.request
import urllib.error


def load_dotenv():
    """Load KEY=VALUE lines from a local .env if present (does not override real env)."""
    for path in (".env", os.path.join(os.path.dirname(__file__), "..", ".env")):
        if os.path.isfile(path):
            with open(path) as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def post(url, data, headers):
    req = urllib.request.Request(url, data=json.dumps(data).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, resp.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def send_via_webhook(webhook_url, text):
    status, body = post(webhook_url, {"text": text}, {"Content-Type": "application/json"})
    ok = status == 200 and body.strip() == "ok"
    return ok, f"HTTP {status}: {body}"


def send_via_bot(token, channel, text):
    status, body = post(
        "https://slack.com/api/chat.postMessage",
        {"channel": channel, "text": text},
        {"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
    )
    try:
        payload = json.loads(body)
        return payload.get("ok", False), body
    except json.JSONDecodeError:
        return False, f"HTTP {status}: {body}"


def main():
    load_dotenv()
    args = sys.argv[1:]
    channel_override = None
    if "--channel" in args:
        i = args.index("--channel")
        channel_override = args[i + 1]
        del args[i:i + 2]

    text = " ".join(args).strip() if args else sys.stdin.read().strip()
    if not text:
        sys.exit("Error: no message provided (pass as argument or via stdin).")

    webhook = os.environ.get("SLACK_WEBHOOK_URL")
    token = os.environ.get("SLACK_BOT_TOKEN")
    channel = channel_override or os.environ.get("SLACK_CHANNEL")

    if webhook:
        ok, detail = send_via_webhook(webhook, text)
        method = "webhook"
    elif token:
        if not channel:
            sys.exit("Error: SLACK_BOT_TOKEN set but no channel (set SLACK_CHANNEL or use --channel).")
        ok, detail = send_via_bot(token, channel, text)
        method = f"bot token -> {channel}"
    else:
        sys.exit(
            "Error: no Slack credential found.\n"
            "  Set SLACK_WEBHOOK_URL, or SLACK_BOT_TOKEN + SLACK_CHANNEL "
            "(in your environment or a local .env file)."
        )

    if ok:
        print(f"✅ Sent to Slack via {method}.")
    else:
        sys.exit(f"❌ Slack API rejected the message ({method}): {detail}")


if __name__ == "__main__":
    main()
