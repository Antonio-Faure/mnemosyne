#!/usr/bin/env bash
# Start a persistent, human-like Chrome accessible over VNC, with CDP on
# 127.0.0.1:9222 (reachable by the mnemosyne container, which shares this netns).
set -euo pipefail

PROFILE_DIR="${CHROME_PROFILE_DIR:-/profile}"
mkdir -p "$PROFILE_DIR"

# Clean locks left by an unclean shutdown (docker rm/restart/kill). Without this,
# Chrome shows the "Chrome isn't stable — restore?" bubble on next start.
rm -f "$PROFILE_DIR"/Singleton* "$PROFILE_DIR"/.com.google.Chrome.* 2>/dev/null || true

echo "[chrome] starting Xvfb on $DISPLAY"
Xvfb "$DISPLAY" -screen 0 1280x900x24 -ac +extension RANDR &

# Wait until the X server actually answers.
for _ in $(seq 1 40); do
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then break; fi
    sleep 0.25
done

echo "[chrome] launching Google Chrome (CDP on 127.0.0.1:9222)"
# --password-store=basic keeps the password manager inside the persistent profile.
# The crash/session flags suppress the "not stable / restore" bubble after an
# unclean restart. --disable-gpu + --disable-dev-shm-usage make headless-ish
# Xvfb Chrome stable (no GPU, small /dev/shm).
google-chrome \
    --user-data-dir="$PROFILE_DIR" \
    --profile-directory=Default \
    --password-store=basic \
    --remote-debugging-address=127.0.0.1 \
    --remote-debugging-port=9222 \
    --no-first-run \
    --no-default-browser-check \
    --noerrdialogs \
    --hide-crash-restore-bubble \
    --disable-session-crashed-bubble \
    --disable-dev-shm-usage \
    --disable-gpu \
    --disable-features=IsolateOrigins,site-per-process,Translate \
    --disable-blink-features=AutomationControlled \
    --window-size=1280,900 \
    --lang=fr-FR \
    --no-sandbox \
    about:blank &
CHROME_PID=$!

echo "[chrome] starting x11vnc on 5900 and noVNC on 6080"
x11vnc -display "$DISPLAY" -forever -shared -nopw -rfbport 5900 >/dev/null 2>&1 &
X11VNC_PID=$!
websockify --web=/usr/share/novnc 6080 localhost:5900 >/dev/null 2>&1 &
WS_PID=$!

shutdown() {
    echo "[chrome] shutting down"
    kill -TERM "$CHROME_PID" "$X11VNC_PID" "$WS_PID" 2>/dev/null || true
    wait "$CHROME_PID" 2>/dev/null || true
    pkill -TERM Xvfb 2>/dev/null || true
    exit 0
}
trap shutdown TERM INT

# If Chrome ever exits, stop the container so Docker restarts it cleanly.
wait "$CHROME_PID" || true
echo "[chrome] Chrome exited"
