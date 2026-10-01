#!/usr/bin/env bash
# Single-container entrypoint: real Chrome (headful under Xvfb, VNC, CDP) + the app.
# Runs as uid 1000 so Chrome keeps its sandbox and shares paths with the agent.
set -euo pipefail

PROFILE_DIR="${CHROME_PROFILE_DIR:-/app/data/chrome-profile}"
mkdir -p "$PROFILE_DIR" /tmp/.X11-unix
chmod 1777 /tmp/.X11-unix 2>/dev/null || true
# clean locks left by an unclean restart
rm -f "$PROFILE_DIR"/Singleton* "$PROFILE_DIR"/.com.google.Chrome.* 2>/dev/null || true
rm -f "/tmp/.X${DISPLAY#:}-lock" /tmp/.X11-unix/X"${DISPLAY#:}" 2>/dev/null || true

echo "[app] starting Xvfb on $DISPLAY"
Xvfb "$DISPLAY" -screen 0 1280x900x24 -ac +extension RANDR &

for _ in $(seq 1 40); do
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then break; fi
    sleep 0.25
done

echo "[app] launching Google Chrome (sandbox enabled, CDP 127.0.0.1:9222)"
google-chrome \
    --user-data-dir="$PROFILE_DIR" \
    --profile-directory=Default \
    --password-store=basic \
    --remote-debugging-address=127.0.0.1 \
    --remote-debugging-port=9222 \
    --no-first-run \
    --no-default-browser-check \
    --noerrdialogs \
    --test-type \
    --hide-crash-restore-bubble \
    --disable-session-crashed-bubble \
    --disable-dev-shm-usage \
    --disable-gpu \
    --disable-features=IsolateOrigins,site-per-process,Translate \
    --disable-blink-features=AutomationControlled \
    --window-size=1280,900 \
    --lang=fr-FR \
    about:blank >/tmp/chrome.log 2>&1 &
CHROME_PID=$!

echo "[app] starting x11vnc on 5900 and noVNC on 6080"
x11vnc -display "$DISPLAY" -forever -shared -nopw -rfbport 5900 >/dev/null 2>&1 &
websockify --web=/usr/share/novnc 6080 localhost:5900 >/dev/null 2>&1 &

echo "[app] launching: $*"
exec "$@"
