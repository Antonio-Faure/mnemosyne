#!/usr/bin/env bash
# Start a persistent Chrome accessible over VNC, CDP on 127.0.0.1:9222
# (reachable by the mnemosyne container, which shares this netns).
#
# Chrome runs as the unprivileged user `chrome` so its sandbox stays enabled:
# no "--no-sandbox / stability and security will suffer" warning.
set -euo pipefail

PROFILE_DIR="${CHROME_PROFILE_DIR:-/profile}"
mkdir -p "$PROFILE_DIR"
chown -R chrome:chrome "$PROFILE_DIR"

# Clean locks left by an unclean shutdown (docker rm/restart/kill), including the
# X server lock: a restart policy reuses the same container's /tmp.
rm -f "$PROFILE_DIR"/Singleton* "$PROFILE_DIR"/.com.google.Chrome.* 2>/dev/null || true
rm -f "/tmp/.X${DISPLAY#:}-lock" /tmp/.X11-unix/X"${DISPLAY#:}" 2>/dev/null || true

mkdir -p /tmp/.X11-unix && chmod 1777 /tmp/.X11-unix

echo "[chrome] starting Xvfb on $DISPLAY"
# -ac: no X access control, so the unprivileged chrome user may connect.
Xvfb "$DISPLAY" -screen 0 1280x900x24 -ac +extension RANDR &

for _ in $(seq 1 40); do
    if xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then break; fi
    sleep 0.25
done

echo "[chrome] launching Google Chrome as user 'chrome' (sandbox enabled)"
# --password-store=basic keeps the password manager inside the persistent profile.
# Crash/session flags suppress the "not stable / restore" bubble.
HOME=/home/chrome gosu chrome google-chrome \
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

wait "$CHROME_PID" || true
echo "[chrome] Chrome exited"
