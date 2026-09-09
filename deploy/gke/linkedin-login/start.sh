#!/usr/bin/env bash
set -euo pipefail
# PID 1 is boot.py so a failed apt-get cannot CrashLoop the container.
exec python3 -u /opt/linkedin-login/boot.py
