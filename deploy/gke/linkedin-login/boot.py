#!/usr/bin/env python3
"""PID-1 supervisor for the in-cluster LinkedIn desktop.

Always bind IPv4 :6080. Never exit on apt/Xvfb/noVNC failures — that is what
turned the previous start.sh into a CrashLoopBackOff (probe connection refused).
"""

from __future__ import annotations

import os
import shutil
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

BOOT = 4
linkedin_login_boot = 4
DISPLAY = os.environ.get("DISPLAY", ":99")
SCRIPT_DIR = Path(os.environ.get("JOBSRSS_LOGIN_SCRIPT_DIR", "/opt/linkedin-login"))
READY_PATH = Path("/tmp/novnc.ready")
STATE = {"mode": "wait", "error": "", "novnc": False}
_httpd: ThreadingHTTPServer | None = None
_httpd_thread: threading.Thread | None = None
_stop = threading.Event()


def log(message: str) -> None:
    print(f"linkedin_login_boot={BOOT} {message}", flush=True)


def which(name: str) -> str | None:
    return shutil.which(name)


def find_novnc_web() -> str | None:
    for candidate in ("/usr/share/novnc", "/usr/share/novnc/www", "/usr/share/novnc/html"):
        if Path(candidate, "vnc.html").is_file():
            return candidate
    return None


def wait_tcp(host: str, port: int, tries: int = 60) -> bool:
    import socket

    for _ in range(tries):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            sock.connect((host, port))
            return True
        except OSError:
            time.sleep(1)
        finally:
            sock.close()
    return False


def page(title: str, body: str, refresh: int | None = None) -> bytes:
    meta = f'<meta http-equiv="refresh" content="{refresh}">' if refresh else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>{title}</title>{meta}
<style>
  body {{ font-family: sans-serif; max-width: 42rem; margin: 3rem auto; line-height: 1.5; }}
  pre {{ background: #111; color: #eee; padding: 1rem; overflow: auto; }}
</style></head>
<body>{body}</body></html>
""".encode("utf-8")


def current_body() -> bytes:
    if STATE["mode"] == "error":
        err = STATE["error"] or "unknown error"
        return page(
            "JobsRSS LinkedIn desktop failed",
            f"<h1>桌面没有启动成功（容器会保持运行，不再死循环）</h1>"
            f"<p>把下面这段发给维护者。不要贴 cookie。</p>"
            f"<pre>{err}</pre>",
        )
    return page(
        "JobsRSS LinkedIn desktop",
        "<h1>正在启动集群桌面（Xvfb / noVNC）</h1>"
        "<p>页面会自动刷新。就绪后地址栏打开 "
        "<code>/vnc.html?autoconnect=1&amp;resize=remote</code></p>"
        "<p>这段路径写在浏览器地址栏，不要写在 Cloud Shell 终端里。</p>",
        refresh=8,
    )


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: bytes, content_type: str) -> None:
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path == "/healthz":
            self._send(200, b'{"status":"ok"}\n', "application/json")
            return
        if path == "/ready":
            if STATE["novnc"] or READY_PATH.exists():
                self._send(200, b'{"ready":true}\n', "application/json")
            else:
                self._send(503, b'{"ready":false}\n', "application/json")
            return
        self._send(200, current_body(), "text/html; charset=utf-8")

    def log_message(self, fmt: str, *args: object) -> None:
        return


def start_status_http() -> None:
    global _httpd, _httpd_thread
    _httpd = ThreadingHTTPServer(("0.0.0.0", 6080), Handler)
    _httpd_thread = threading.Thread(target=_httpd.serve_forever, daemon=True)
    _httpd_thread.start()
    if not wait_tcp("127.0.0.1", 6080, 20):
        raise RuntimeError("status page failed to bind 0.0.0.0:6080")
    log("status_http_listen :6080 /healthz /vnc.html")


def stop_status_http() -> None:
    global _httpd, _httpd_thread
    if _httpd is None:
        return
    log("status_http_stop handing :6080 to websockify")
    _httpd.shutdown()
    if _httpd_thread is not None:
        _httpd_thread.join(timeout=8)
    _httpd.server_close()
    _httpd = None
    _httpd_thread = None
    time.sleep(0.5)


def ensure_packages() -> None:
    if which("Xvfb") and which("x11vnc") and find_novnc_web():
        log("desktop_packages_present skip apt-get")
        return
    log("desktop_packages_missing trying runtime apt-get (prefer prebuilt login image)")
    env = os.environ.copy()
    env["DEBIAN_FRONTEND"] = "noninteractive"
    update = subprocess.run(["apt-get", "update"], env=env, capture_output=True, text=True)
    if update.returncode != 0:
        raise RuntimeError(f"apt-get update failed:\n{update.stderr or update.stdout}")
    install = subprocess.run(
        [
            "apt-get",
            "install",
            "-y",
            "--no-install-recommends",
            "xvfb",
            "x11vnc",
            "novnc",
            "websockify",
        ],
        env=env,
        capture_output=True,
        text=True,
    )
    if install.returncode != 0:
        raise RuntimeError(f"apt-get install failed:\n{install.stderr or install.stdout}")
    if not (which("Xvfb") and which("x11vnc") and find_novnc_web()):
        raise RuntimeError("apt-get finished but Xvfb/x11vnc/noVNC are still missing")


def start_xvfb() -> subprocess.Popen[bytes]:
    display_num = DISPLAY.lstrip(":")
    sock = Path(f"/tmp/.X11-unix/X{display_num}")
    proc = subprocess.Popen(
        ["Xvfb", DISPLAY, "-screen", "0", "1280x800x24", "-ac", "+extension", "RANDR"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    for _ in range(30):
        if sock.exists() and proc.poll() is None:
            log(f"xvfb_ready display={DISPLAY}")
            return proc
        time.sleep(1)
    raise RuntimeError(f"Xvfb did not create {sock} (exit={proc.poll()})")


def start_x11vnc() -> subprocess.Popen[bytes]:
    proc = subprocess.Popen(
        [
            "x11vnc",
            "-display",
            DISPLAY,
            "-forever",
            "-shared",
            "-nopw",
            "-listen",
            "127.0.0.1",
            "-rfbport",
            "5900",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if not wait_tcp("127.0.0.1", 5900, 30):
        raise RuntimeError(f"x11vnc did not listen on 127.0.0.1:5900 (exit={proc.poll()})")
    log("x11vnc_ready :5900")
    return proc


def start_websockify(novnc_web: str) -> subprocess.Popen[bytes]:
    bind = "0.0.0.0:6080"
    if which("websockify"):
        cmd = ["websockify", "--web", novnc_web, bind, "127.0.0.1:5900"]
    else:
        cmd = [sys.executable, "-m", "websockify", "--web", novnc_web, bind, "127.0.0.1:5900"]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not wait_tcp("127.0.0.1", 6080, 20):
        proc.kill()
        cmd[-3] = "6080"
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if not wait_tcp("127.0.0.1", 6080, 20):
            raise RuntimeError(f"websockify did not listen on :6080 (exit={proc.poll()})")
    log(f"novnc_ready web={novnc_web}")
    return proc


def mark_ready() -> None:
    READY_PATH.write_text("ready\n", encoding="utf-8")
    STATE["novnc"] = True
    STATE["mode"] = "novnc"
    log("wrote /tmp/novnc.ready")


def run_session() -> None:
    script = SCRIPT_DIR / "session.py"
    while not _stop.is_set():
        log(f"session_start {script}")
        proc = subprocess.Popen([sys.executable, "-u", str(script)])
        while not _stop.is_set():
            try:
                if proc.wait(timeout=2) is not None:
                    break
            except subprocess.TimeoutExpired:
                continue
        if _stop.is_set():
            proc.terminate()
            return
        log(f"session.py exited {proc.returncode}; restart in 5s")
        time.sleep(5)


def desktop_main() -> None:
    try:
        ensure_packages()
        novnc_web = find_novnc_web()
        if not novnc_web:
            raise RuntimeError("noVNC web files not found")
        xvfb = start_xvfb()
        x11vnc = start_x11vnc()
        stop_status_http()
        websockify = start_websockify(novnc_web)
        mark_ready()
        session_thread = threading.Thread(target=run_session, daemon=True)
        session_thread.start()
        while not _stop.is_set():
            if xvfb.poll() is not None:
                raise RuntimeError(f"Xvfb exited {xvfb.returncode}")
            if x11vnc.poll() is not None:
                raise RuntimeError(f"x11vnc exited {x11vnc.returncode}")
            if websockify.poll() is not None:
                log("websockify exited; restarting")
                websockify = start_websockify(novnc_web)
            time.sleep(2)
    except Exception as exc:
        STATE["mode"] = "error"
        STATE["error"] = str(exc)
        STATE["novnc"] = False
        READY_PATH.unlink(missing_ok=True)
        log(f"desktop_failed {exc}")
        if _httpd is None and not _stop.is_set():
            try:
                start_status_http()
            except Exception as bind_exc:
                log(f"status_http_rebind_failed {bind_exc}")


def handle_signal(signum: int, _frame: object) -> None:
    log(f"signal {signum}")
    _stop.set()
    raise SystemExit(0)


def main() -> None:
    log(f"start display={DISPLAY}")
    READY_PATH.unlink(missing_ok=True)
    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)
    start_status_http()
    threading.Thread(target=desktop_main, daemon=True).start()
    while not _stop.is_set():
        time.sleep(1)


if __name__ == "__main__":
    main()
