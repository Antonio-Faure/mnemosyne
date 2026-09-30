#!/usr/bin/env bash
# Start a persistent, human-like Chrome accessible over CDP + VNC.
set -euo pipefail

PROFILE_DIR="${CHROME_PROFILE_DIR:-/profile}"
mkdir -p "$PROFILE_DIR"

echo "[chrome] starting Xvfb on $DISPLAY"
Xvfb "$DISPLAY" -screen 0 1280x900x24 -ac +extension RANDR &

# Wait for the X server to be ready.
for _ in $(seq 1 30); do
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then break; fi
    sleep 0.5
done

echo "[chrome] launching Google Chrome (CDP on 9222)"
google-chrome \
    --user-data-dir="$PROFILE_DIR" \
    --remote-debugging-address=0.0.0.0 \
    --remote-debugging-port=9222 \
    --no-first-run \
    --no-default-browser-check \
    --disable-blink-features=AutomationControlled \
    --disable-features=IsolateOrigins,site-per-process \
    --window-size=1280,900 \
    --lang=fr-FR \
    --no-sandbox \
    about:blank &

echo "[chrome] starting x11vnc on 5900 and noVNC on 6080"
x11vnc -display "$DISPLAY" -forever -shared -nopw -rfbport 5900 >/dev/null 2>&1 &
websockify --web=/usr/share/novnc 6080 localhost:5900 >/dev/null 2>&1 &

wait
