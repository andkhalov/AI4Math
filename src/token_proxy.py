"""Lightweight token-counting proxy between Goose and Yandex AI Studio.

Sits on localhost, forwards all requests to the real Yandex endpoint,
parses usage from responses (including SSE streaming), and blocks new
requests when the daily budget is exceeded.

Usage (from bin/ai4math.py — auto-started, not user-facing):
    python src/token_proxy.py [--port PORT] [--upstream URL] [--limit N]

The proxy writes daily totals to ~/.ai4math_budget.json and reads it
back on startup so budget survives process restarts.
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading
from datetime import date
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError

UPSTREAM = os.environ.get("AI4MATH_UPSTREAM", "https://llm.api.cloud.yandex.net")
DAILY_LIMIT = int(os.environ.get("AI4MATH_DAILY_TOKEN_LIMIT", "2000000"))
BUDGET_FILE = Path.home() / ".ai4math_budget.json"

_lock = threading.Lock()
_today: str = ""
_used: int = 0


def _load_budget() -> tuple[str, int]:
    try:
        d = json.loads(BUDGET_FILE.read_text())
        return d.get("date", ""), d.get("tokens", 0)
    except Exception:
        return "", 0


def _save_budget(day: str, tokens: int) -> None:
    try:
        BUDGET_FILE.write_text(json.dumps({"date": day, "tokens": tokens}))
    except Exception:
        pass


def _add_tokens(n: int) -> int:
    global _today, _used
    today = date.today().isoformat()
    with _lock:
        if _today != today:
            _today = today
            _used = 0
            saved_day, saved_tok = _load_budget()
            if saved_day == today:
                _used = saved_tok
        _used += n
        _save_budget(_today, _used)
        return _used


def _get_used() -> int:
    global _today, _used
    today = date.today().isoformat()
    with _lock:
        if _today != today:
            _today = today
            _used = 0
            saved_day, saved_tok = _load_budget()
            if saved_day == today:
                _used = saved_tok
        return _used


class ProxyHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def do_POST(self):
        used = _get_used()
        if used >= DAILY_LIMIT:
            body = json.dumps({
                "error": {
                    "message": (
                        f"[AI4Math] Суточный лимит токенов исчерпан "
                        f"({used:,} / {DAILY_LIMIT:,}). "
                        f"Лимит сбросится в полночь. Заверши сессию (/exit)."
                    ),
                    "type": "rate_limit_exceeded",
                    "code": "daily_token_limit",
                }
            }).encode()
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        content_len = int(self.headers.get("Content-Length", 0))
        req_body = self.rfile.read(content_len) if content_len else b""

        url = f"{UPSTREAM}{self.path}"
        headers = {
            k: v for k, v in self.headers.items()
            if k.lower() not in ("host", "transfer-encoding")
        }

        req = Request(url, data=req_body, headers=headers, method="POST")
        try:
            resp = urlopen(req, timeout=120)
        except HTTPError as e:
            self.send_response(e.code)
            for k, v in e.headers.items():
                if k.lower() not in ("transfer-encoding",):
                    self.send_header(k, v)
            self.end_headers()
            self.wfile.write(e.read())
            return

        ct = resp.headers.get("Content-Type", "")
        is_sse = "text/event-stream" in ct

        self.send_response(resp.status)
        for k, v in resp.headers.items():
            if k.lower() not in ("transfer-encoding",):
                self.send_header(k, v)
        self.end_headers()

        if is_sse:
            self._handle_sse(resp)
        else:
            body = resp.read()
            self.wfile.write(body)
            self._count_tokens_json(body)

    def _handle_sse(self, resp):
        last_data = b""
        for raw_line in resp:
            self.wfile.write(raw_line)
            try:
                self.wfile.flush()
            except Exception:
                break
            line = raw_line.strip()
            if line.startswith(b"data: ") and line != b"data: [DONE]":
                last_data = line[6:]
        self._count_tokens_json(last_data)

    def _count_tokens_json(self, body: bytes):
        try:
            d = json.loads(body)
        except Exception:
            return
        usage = d.get("usage")
        if not usage:
            for choice in d.get("choices", []):
                usage = choice.get("usage")
                if usage:
                    break
        if usage and isinstance(usage, dict):
            total = usage.get("total_tokens") or 0
            if total > 0:
                new_used = _add_tokens(total)
                if new_used >= DAILY_LIMIT:
                    sys.stderr.write(
                        f"[token_proxy] daily limit reached: {new_used:,}/{DAILY_LIMIT:,}\n"
                    )


def main():
    global UPSTREAM, DAILY_LIMIT

    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=0)
    p.add_argument("--upstream", default=UPSTREAM)
    p.add_argument("--limit", type=int, default=DAILY_LIMIT)
    args = p.parse_args()

    UPSTREAM = args.upstream
    DAILY_LIMIT = args.limit

    server = HTTPServer(("127.0.0.1", args.port), ProxyHandler)
    port = server.server_address[1]
    # Print port on stdout so the parent process can read it
    print(port, flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
