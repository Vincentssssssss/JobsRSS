#!/usr/bin/env python3
"""Headed Chromium on DISPLAY, plus an HTTP login panel for Cloud Shell."""

from __future__ import annotations

import json
import os
import queue
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from playwright.sync_api import sync_playwright

LOGIN_URL = "https://www.linkedin.com/login"
ALLOWED_DOMAINS = ("linkedin.com",)
SESSION_DIR = Path(os.environ.get("JOBSRSS_SESSION_DIR", "/session"))
STATE_PATH = SESSION_DIR / "linkedin_state.json"
PROFILE_DIR = SESSION_DIR / "profile"
LISTEN_PORT = int(os.environ.get("JOBSRSS_SESSION_PORT", "8080"))

_context = None
_lock = threading.Lock()
_actions: queue.Queue = queue.Queue()


VIEW_HTML = """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>JobsRSS LinkedIn login</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
  body { font-family: sans-serif; margin: 1rem; line-height: 1.45; }
  .row { display: flex; gap: 1rem; flex-wrap: wrap; }
  form { margin: 0.5rem 0; }
  label { display: inline-block; min-width: 4rem; }
  input[type=text], input[type=password], input[type=url] { width: 16rem; }
  img { max-width: 100%; border: 1px solid #ccc; cursor: crosshair; background: #eee; }
  .hint { color: #444; }
  code { background: #f3f3f3; padding: 0 0.25rem; }
</style>
</head>
<body>
<h1>集群里的 LinkedIn 登录页</h1>
<p class="hint">Cloud Shell Web Preview 改地址栏会跳回空白页，而且常常接不上 noVNC 的 WebSocket。这个页面是普通 HTTP，不要改地址栏。</p>
<p>当前：<code id="url">...</code> / <span id="title"></span></p>
<div class="row">
  <form method="post" action="/action">
    <input type="hidden" name="op" value="fill_login">
    <div><label>邮箱</label><input type="text" name="email" autocomplete="username"></div>
    <div><label>密码</label><input type="password" name="password" autocomplete="current-password"></div>
    <button type="submit">填入并点登录</button>
  </form>
  <form method="post" action="/action">
    <input type="hidden" name="op" value="fill_otp">
    <div><label>2FA</label><input type="text" name="code" inputmode="numeric"></div>
    <button type="submit">填入验证码并回车</button>
  </form>
</div>
<form method="post" action="/action">
  <input type="hidden" name="op" value="type">
  <label>向当前焦点打字</label>
  <input type="text" name="text">
  <button type="submit">输入</button>
  <button type="submit" name="op" value="enter">回车</button>
</form>
<p class="hint">也可以点下面截图（坐标会按 1280x800 换算）。Feed 出来后回到 Cloud Shell 跑 <code>linkedin-session.sh --export</code>。</p>
<p><img id="shot" src="/screenshot" alt="LinkedIn screenshot" width="1280"></p>
<script>
function refresh() {
  fetch("/status").then(r => r.json()).then(s => {
    document.getElementById("url").textContent = s.url || "";
    document.getElementById("title").textContent = s.title || "";
  }).catch(() => {});
  const img = document.getElementById("shot");
  img.src = "/screenshot?t=" + Date.now();
}
setInterval(refresh, 2500);
refresh();
document.getElementById("shot").addEventListener("click", (ev) => {
  const img = ev.currentTarget;
  const rect = img.getBoundingClientRect();
  const x = Math.round((ev.clientX - rect.left) * 1280 / rect.width);
  const y = Math.round((ev.clientY - rect.top) * 800 / rect.height);
  const body = new URLSearchParams({op: "click", x: String(x), y: String(y)});
  fetch("/action", {method: "POST", headers: {"Content-Type": "application/x-www-form-urlencoded"}, body}).then(refresh);
});
</script>
</body>
</html>
""".encode("utf-8")


class BrowserAction:
    def __init__(self, name: str, payload: dict) -> None:
        self.name = name
        self.payload = payload
        self.event = threading.Event()
        self.result: object = None
        self.error: str | None = None


def call_browser(name: str, payload: dict | None = None, timeout: float = 60) -> object:
    action = BrowserAction(name, payload or {})
    _actions.put(action)
    if not action.event.wait(timeout):
        raise TimeoutError("browser is busy")
    if action.error:
        raise RuntimeError(action.error)
    return action.result


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
        raise RuntimeError("no LinkedIn cookies yet; finish login first")
    SESSION_DIR.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
    os.chmod(STATE_PATH, 0o600)
    return {"saved": str(STATE_PATH), "cookies": len(filtered["cookies"])}


def handle_browser_action(page: object, action: BrowserAction) -> None:
    name = action.name
    data = action.payload
    if name == "screenshot":
        action.result = page.screenshot(type="png")
        return
    if name == "status":
        action.result = {"url": page.url, "title": page.title()}
        return
    if name == "fill_login":
        email = str(data.get("email") or "")
        password = str(data.get("password") or "")
        page.locator("#username, input[name='session_key']").first.fill(email, timeout=10000)
        page.locator("#password, input[name='session_password']").first.fill(password, timeout=10000)
        page.locator("button[type=submit]").first.click(timeout=10000)
        page.wait_for_timeout(1500)
        action.result = {"url": page.url}
        return
    if name == "fill_otp":
        code = str(data.get("code") or "")
        box = page.locator(
            "input[name='pin'], input[autocomplete='one-time-code'], input[name='otp'], input[type='tel']"
        ).first
        box.fill(code, timeout=10000)
        page.keyboard.press("Enter")
        page.wait_for_timeout(1500)
        action.result = {"url": page.url}
        return
    if name == "type":
        page.keyboard.type(str(data.get("text") or ""), delay=20)
        action.result = {"url": page.url}
        return
    if name == "enter":
        page.keyboard.press("Enter")
        action.result = {"url": page.url}
        return
    if name == "click":
        page.mouse.click(int(data["x"]), int(data["y"]))
        page.wait_for_timeout(400)
        action.result = {"url": page.url}
        return
    if name == "goto":
        page.goto(str(data.get("url") or LOGIN_URL), wait_until="domcontentloaded", timeout=60000)
        action.result = {"url": page.url}
        return
    raise RuntimeError(f"unknown op {name}")


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(len(body)))
        self.send_header("cache-control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload: dict) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"), "application/json")

    def _read_form(self) -> dict[str, str]:
        length = int(self.headers.get("content-length") or 0)
        raw = self.rfile.read(length) if length else b""
        ctype = self.headers.get("content-type", "")
        if "json" in ctype:
            return json.loads(raw.decode("utf-8") or "{}")
        parsed = parse_qs(raw.decode("utf-8"), keep_blank_values=True)
        return {key: values[-1] if values else "" for key, values in parsed.items()}

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path in ("/", "/view"):
            self._send(200, VIEW_HTML, "text/html; charset=utf-8")
            return
        if path == "/health":
            self._json(200, {"status": "ok", "browser": _context is not None})
            return
        if path == "/status":
            try:
                self._json(200, call_browser("status"))  # type: ignore[arg-type]
            except Exception as exc:
                self._json(503, {"error": str(exc)})
            return
        if path == "/screenshot":
            try:
                png = call_browser("screenshot")
                self._send(200, png if isinstance(png, bytes) else b"", "image/png")
            except Exception as exc:
                self._json(503, {"error": str(exc)})
            return
        self._json(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/export":
            try:
                self._json(200, export_state())
            except Exception as exc:
                self._json(409, {"error": str(exc)})
            return
        if path != "/action":
            self._json(404, {"error": "not_found"})
            return
        try:
            form = self._read_form()
            op = str(form.get("op") or "status")
            result = call_browser(op, form)
            if self.headers.get("accept") == "application/json":
                self._json(200, result if isinstance(result, dict) else {"ok": True})
                return
            self.send_response(303)
            self.send_header("Location", "/view")
            self.end_headers()
        except Exception as exc:
            self._json(409, {"error": str(exc)})

    def log_message(self, format: str, *args: object) -> None:
        path = args[0] if args else ""
        if "screenshot" in str(path) or "status" in str(path):
            return
        print(f"session_http {path}")


def main() -> None:
    global _context
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", LISTEN_PORT), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print(f"session_http_listen port={LISTEN_PORT} /view /screenshot")

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
        print("linkedin_login_ready use Web Preview :8080 /  or noVNC :6080")
        while True:
            try:
                action = _actions.get(timeout=0.4)
            except queue.Empty:
                continue
            try:
                handle_browser_action(page, action)
            except Exception as exc:
                action.error = str(exc)
            finally:
                action.event.set()


if __name__ == "__main__":
    main()
