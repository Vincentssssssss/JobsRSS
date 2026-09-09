#!/usr/bin/env bash
set -euo pipefail

# Headed Chromium on the cluster egress IP, exposed through noVNC on :6080.
# Bind IPv4 :6080 before apt-get so Cloud Shell port-forward does not get
# "connection refused" during the first-start package install.

export DEBIAN_FRONTEND=noninteractive
export DISPLAY="${DISPLAY:-:99}"
SESSION_DIR="${JOBSRSS_SESSION_DIR:-/session}"
mkdir -p "${SESSION_DIR}"

wait_tcp() {
  local host="$1" port="$2" tries="${3:-60}"
  python3 - "$host" "$port" "$tries" <<'PY'
import socket, sys, time
host, port, tries = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
for _ in range(tries):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(1)
    try:
        sock.connect((host, port))
        sys.exit(0)
    except OSError:
        time.sleep(1)
    finally:
        sock.close()
sys.exit(1)
PY
}

wait_http() {
  python3 - "$1" "$2" <<'PY'
import sys, time, urllib.error, urllib.request
url, tries = sys.argv[1], int(sys.argv[2])
for _ in range(tries):
    try:
        urllib.request.urlopen(url, timeout=2)
        sys.exit(0)
    except urllib.error.HTTPError as exc:
        if exc.code < 500:
            sys.exit(0)
    except Exception:
        time.sleep(1)
        continue
    time.sleep(1)
sys.exit(1)
PY
}

start_wait_page() {
  python3 - <<'PY' >/tmp/wait6080.log 2>&1 &
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BODY = b"""<!doctype html>
<html lang="zh-CN">
<head><meta charset="utf-8"><title>JobsRSS LinkedIn desktop</title>
<meta http-equiv="refresh" content="8">
<style>
  body { font-family: sans-serif; max-width: 40rem; margin: 3rem auto; line-height: 1.5; }
</style></head>
<body>
<h1>正在集群里安装桌面（Xvfb / noVNC）</h1>
<p>第一次启动要 1–3 分钟。页面会自动刷新。</p>
<p>就绪后请打开：<code>/vnc.html?autoconnect=1&amp;resize=remote</code></p>
<p>这段路径写在<strong>浏览器地址栏</strong>，不要写在 Cloud Shell 终端里。</p>
</body></html>
"""


class Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/vnc.html", "/vnc_lite.html"):
            self.send_response(503)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"noVNC is still installing")
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(BODY)))
        self.end_headers()
        self.wfile.write(BODY)

    def log_message(self, fmt: str, *args: object) -> None:
        return


ThreadingHTTPServer(("0.0.0.0", 6080), Handler).serve_forever()
PY
  echo $! >/tmp/wait6080.pid
  wait_tcp 127.0.0.1 6080 20
  echo "wait_page_listen :6080 (installing desktop packages)"
}

stop_wait_page() {
  if [ -f /tmp/wait6080.pid ]; then
    kill "$(cat /tmp/wait6080.pid)" >/dev/null 2>&1 || true
    rm -f /tmp/wait6080.pid
    sleep 1
  fi
}

echo "linkedin_login_start display=${DISPLAY}"
start_wait_page

if ! command -v Xvfb >/dev/null || ! command -v x11vnc >/dev/null; then
  echo "Installing xvfb/x11vnc/novnc (first start only for this pod)..."
  apt-get update
  apt-get install -y --no-install-recommends xvfb x11vnc novnc websockify python3-websockify || \
    apt-get install -y --no-install-recommends xvfb x11vnc novnc websockify
fi

NOVNC_WEB=""
for candidate in /usr/share/novnc /usr/share/novnc/www /usr/share/novnc/html; do
  if [ -f "${candidate}/vnc.html" ]; then
    NOVNC_WEB="${candidate}"
    break
  fi
done
if [ -z "${NOVNC_WEB}" ]; then
  echo "noVNC web files not found after apt-get"
  ls -la /usr/share/novnc 2>/dev/null || true
  exit 1
fi
echo "novnc_web=${NOVNC_WEB}"

Xvfb "${DISPLAY}" -screen 0 1280x800x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
for _ in $(seq 1 30); do
  if [ -S /tmp/.X11-unix/X99 ] || [ -S /tmp/.X11-unix/X"${DISPLAY#:}" ]; then
    break
  fi
  sleep 1
done
if [ ! -S /tmp/.X11-unix/X99 ] && [ ! -S /tmp/.X11-unix/X"${DISPLAY#:}" ]; then
  echo "Xvfb did not create a display socket"
  cat /tmp/xvfb.log || true
  exit 1
fi

x11vnc -display "${DISPLAY}" -forever -shared -nopw -listen 127.0.0.1 -rfbport 5900 >/tmp/x11vnc.log 2>&1 &
if ! wait_tcp 127.0.0.1 5900 30; then
  echo "x11vnc did not listen on 127.0.0.1:5900"
  cat /tmp/x11vnc.log || true
  exit 1
fi

stop_wait_page

start_websockify() {
  local bind="$1"
  if [ -f /tmp/novnc.pid ]; then
    kill "$(cat /tmp/novnc.pid)" >/dev/null 2>&1 || true
    rm -f /tmp/novnc.pid
    sleep 1
  fi
  if command -v websockify >/dev/null; then
    websockify --web="${NOVNC_WEB}" "${bind}" 127.0.0.1:5900 >/tmp/novnc.log 2>&1 &
  else
    python3 -m websockify --web="${NOVNC_WEB}" "${bind}" 127.0.0.1:5900 >/tmp/novnc.log 2>&1 &
  fi
  echo $! >/tmp/novnc.pid
}

start_websockify "0.0.0.0:6080"
if ! wait_tcp 127.0.0.1 6080 15; then
  echo "websockify 0.0.0.0:6080 failed, retrying :6080"
  cat /tmp/novnc.log || true
  start_websockify "6080"
fi
if ! wait_http "http://127.0.0.1:6080/vnc.html" 20; then
  echo "noVNC did not serve /vnc.html on 127.0.0.1:6080"
  echo "--- novnc.log ---"
  cat /tmp/novnc.log || true
  echo "--- x11vnc.log ---"
  cat /tmp/x11vnc.log || true
  exit 1
fi

echo "noVNC is listening on IPv4 :6080"
echo "Open this path in the browser address bar after Web Preview, not in Cloud Shell:"
echo "  /vnc.html?autoconnect=1&resize=remote"
echo "After LinkedIn shows your feed: bash deploy/gke/scripts/linkedin-session.sh --export"
exec python3 /opt/linkedin-login/session.py
