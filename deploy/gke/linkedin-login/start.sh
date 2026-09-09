#!/usr/bin/env bash
set -euo pipefail

# Install a minimal X11 + noVNC stack in the existing Playwright API image,
# then keep a headed Chromium on the cluster egress IP for LinkedIn login.

export DEBIAN_FRONTEND=noninteractive
export DISPLAY="${DISPLAY:-:99}"
SESSION_DIR="${JOBSRSS_SESSION_DIR:-/session}"
mkdir -p "${SESSION_DIR}"

if ! command -v Xvfb >/dev/null || ! command -v x11vnc >/dev/null || ! command -v websockify >/dev/null; then
  echo "Installing xvfb/x11vnc/novnc (first start only for this pod)..."
  apt-get update
  apt-get install -y --no-install-recommends xvfb x11vnc novnc websockify
fi

NOVNC_WEB=""
for candidate in /usr/share/novnc /usr/share/novnc/www; do
  if [ -f "${candidate}/vnc.html" ]; then
    NOVNC_WEB="${candidate}"
    break
  fi
done
if [ -z "${NOVNC_WEB}" ]; then
  echo "noVNC web files not found"
  exit 1
fi

Xvfb "${DISPLAY}" -screen 0 1280x800x24 -ac +extension RANDR >/tmp/xvfb.log 2>&1 &
sleep 1
x11vnc -display "${DISPLAY}" -forever -shared -nopw -listen 0.0.0.0 -rfbport 5900 >/tmp/x11vnc.log 2>&1 &
websockify --web="${NOVNC_WEB}" 6080 localhost:5900 >/tmp/novnc.log 2>&1 &

echo "noVNC is on :6080  (kubectl port-forward svc/linkedin-login 6080:6080)"
echo "After LinkedIn shows your feed, run: bash deploy/gke/scripts/linkedin-session.sh --export"
exec python3 /opt/linkedin-login/session.py
