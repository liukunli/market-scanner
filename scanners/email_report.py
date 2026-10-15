"""Send the pre-market report by email.

Preferred: Resend HTTPS API (works through Claude's cloud sandbox proxy).
    RESEND_API_KEY   Resend API key (starts with "re_")
    REPORT_TO        recipient (default: liukunli@msu.edu)
    REPORT_FROM      sender (default: "Market Scanner <onboarding@resend.dev>",
                     which Resend allows for sending to your own signup email)

Fallback: Gmail SMTP, used only if RESEND_API_KEY is not set.
    GMAIL_USER, GMAIL_APP_PASSWORD

Usage:
    python3 -m scanners.email_report premarket_report.txt
"""
from __future__ import annotations

import json
import os
import smtplib
import socket
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from email.message import EmailMessage

DEFAULT_TO = "liukunli@msu.edu"
DEFAULT_FROM = "Market Scanner <onboarding@resend.dev>"


# --- Resend ---------------------------------------------------------------------
def _send_resend(api_key: str, subject: str, body: str, to: str) -> str:
    payload = json.dumps({
        "from": os.environ.get("REPORT_FROM") or DEFAULT_FROM,
        "to": [to],
        "subject": subject,
        "text": body,
    }).encode()
    req = urllib.request.Request(
        "https://api.resend.com/emails", data=payload, method="POST",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json",
                 "User-Agent": "market-scanner/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"Resend send failed: HTTP {e.code} {e.read().decode(errors='replace')}")
    if not result.get("id"):
        raise RuntimeError(f"Resend send failed: {result}")
    return result["id"]


# --- Gmail SMTP fallback (tunnels through HTTPS_PROXY when set) ----------------
def _tunnel(host: str, port: int, timeout: float) -> socket.socket:
    proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if not proxy:
        return socket.create_connection((host, port), timeout)
    p = urllib.parse.urlparse(proxy)
    sock = socket.create_connection((p.hostname, p.port), timeout)
    sock.sendall(f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode())
    resp = b""
    while b"\r\n\r\n" not in resp:
        chunk = sock.recv(4096)
        if not chunk:
            break
        resp += chunk
    status = resp.split(b"\r\n", 1)[0]
    if b" 200 " not in status + b" ":
        sock.close()
        raise OSError(f"proxy CONNECT to {host}:{port} failed: {status.decode(errors='replace')}")
    return sock


class _ProxiedSMTPSSL(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        return self.context.wrap_socket(_tunnel(host, port, timeout), server_hostname=host)


def _send_gmail(user: str, password: str, subject: str, body: str, to: str) -> str:
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = user, to, subject
    msg.set_content(body)
    with _ProxiedSMTPSSL("smtp.gmail.com", 465, context=ssl.create_default_context(),
                         timeout=30) as smtp:
        smtp.login(user, password.replace(" ", ""))
        smtp.send_message(msg)
    return "gmail"


def send(subject: str, body: str, to: str | None = None) -> str:
    to = to or os.environ.get("REPORT_TO") or DEFAULT_TO
    key = os.environ.get("RESEND_API_KEY")
    if key:
        return _send_resend(key, subject, body, to)
    user, pw = os.environ.get("GMAIL_USER"), os.environ.get("GMAIL_APP_PASSWORD")
    if user and pw:
        return _send_gmail(user, pw, subject, body, to)
    raise RuntimeError("No email credentials: set RESEND_API_KEY (or GMAIL_USER + GMAIL_APP_PASSWORD)")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "premarket_report.txt"
    with open(path) as fh:
        body = fh.read()
    subject = body.splitlines()[0] if body else "Pre-market gappers"
    print(f"sent ({send(subject, body)}): {subject}")
