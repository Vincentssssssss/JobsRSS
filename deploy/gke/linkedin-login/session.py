#!/usr/bin/env python3
"""Keep a headed Chromium session on DISPLAY and export LinkedIn storage state."""

from __future__ import annotations

import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import sync_playwright

SITE = "linkedin"
LOGIN_URL = "https://www.linkedin.com/login"
ALLOWED_DOMAINS = ("linkedin.com",)
SESSION_DIR = Path(os.environ.get("JOBSRSS_SESSION_DIR", "/session"))
STATE_PATH = SESSION_DIR / "linkedin_state.json"
PROFILE_DIR = SESSION_DIR / "profile"
LISTEN_PORT = int(os.environ.get("JOBSRSS_SESSION_PORT", "8080"))

_context = None
_lock = threading.Lock()


def domain_matches(host: str, allowed_domains: tuple[str, ...]) -> bool:
    normalized = host.lower().lstrip(".").rstrip(".")
    return any(
        normalized == allowed or normalized.endswith(f".{allowed}")
        for allowed in allowed_domains
    )


def filter_storage_state(state: dict) -> dict:
    cookies = [
        cookie
        for cookie in state.get("cookies", [])
        if domain_matches(str(cookie.get("domain", "")), ALLOWED_DOMAINS)
    ]
    origins = []
    for origin in state.get("origins", []):
        host = urlparse(str(origin.get("origin", ""))).hostname or ""
        if domain_matches(host, ALLOWED_DOMAINS):
            origins.append(origin)
    return {"cookies": cookies, "origins": origins}


def export_state() -> dict:
    if _context is None:
        raise RuntimeError("browser is not ready")
    with _lock:
        filtered = filter_storage_state(_context.storage_state())
    if not filtered["cookies"]:
        raise RuntimeError("no LinkedIn cookies yet; finish login in the noVNC window")
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(STATE_PATH, 0o600)
    return {"saved": str(STATE_PATH), "cookies": len(filtered["cookies"])}


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            self._json(200, {"status": "ok", "browser": _context is not None})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/export":
            self._json(404, {"error": "not_found"})
            return
        try:
            self._json(200, export_state())
        except Exception as exc:
            self._json(409, {"error": str(exc)})

    def log_message(self, format: str, *args: object) -> None:
        print(f"session_http {args[0]}")


def main() -> None:
    global _context
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"session_http_listen port={LISTEN_PORT}")

    with sync_playwright() as playwright:
        _context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE_DIR),
            headless=False,
            ignore_https_errors=True,
            args=[
                "--no-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                "--window-size=1280,800",
            ],
            viewport={"width": 1280, "height": 800},
        )
        page = _context.pages[0] if _context.pages else _context.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        print("linkedin_login_ready open noVNC, complete login and 2FA, then POST /export")
        while True:
            page.wait_for_timeout(60_000)


if __name__ == "__main__":
    main()
