"""Send the pre-market report by email via Gmail SMTP.

Credentials come from env vars (never commit them):
    GMAIL_USER          sender Gmail address, e.g. liukunli001@gmail.com
    GMAIL_APP_PASSWORD  a Google "app password" (16 chars) for that account
    REPORT_TO           recipient (default: liukunli@msu.edu)

If HTTPS_PROXY is set (as in Claude's cloud sandbox), the SMTP connection is
tunnelled through it with an HTTP CONNECT, since direct egress is blocked there.

Usage:
    python3 -m scanners.email_report premarket_report.txt
"""
from __future__ import annotations

import os
import smtplib
import socket
import ssl
import sys
import urllib.parse
from email.message import EmailMessage

SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465
DEFAULT_TO = "liukunli@msu.edu"


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
        raw = _tunnel(host, port, timeout)
        return self.context.wrap_socket(raw, server_hostname=host)


def send(subject: str, body: str, to: str | None = None) -> None:
    user = os.environ.get("GMAIL_USER")
    password = os.environ.get("GMAIL_APP_PASSWORD")
    if not user or not password:
        raise RuntimeError("GMAIL_USER / GMAIL_APP_PASSWORD not set")
    to = to or os.environ.get("REPORT_TO") or DEFAULT_TO

    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = user, to, subject
    msg.set_content(body)

    ctx = ssl.create_default_context()
    with _ProxiedSMTPSSL(SMTP_HOST, SMTP_PORT, context=ctx, timeout=30) as smtp:
        smtp.login(user, password.replace(" ", ""))
        smtp.send_message(msg)


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "premarket_report.txt"
    with open(path) as fh:
        body = fh.read()
    first = body.splitlines()[0] if body else "Pre-market gappers"
    send(first, body)
    print(f"sent: {first}")
