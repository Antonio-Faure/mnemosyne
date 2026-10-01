#!/usr/bin/env bash
# Record the agent's Chrome screen (Xvfb :99) for N seconds into data/agent-recording.mp4.
# Usage: scripts/record-agent.sh [seconds]   (default 60)
set -euo pipefail
cd "$(dirname "$0")/.."
SECS="${1:-60}"
docker exec -d mnemosyne-chrome-1 ffmpeg -y -f x11grab -framerate 12 \
    -video_size 1280x900 -i :99 -t "$SECS" -pix_fmt yuv420p -movflags +faststart \
    /tmp/agent-recording.mp4
echo "enregistrement ${SECS}s (lance une session dans un autre terminal : mnemosyne warmup --minutes 2)"
sleep "$((SECS + 3))"
docker cp mnemosyne-chrome-1:/tmp/agent-recording.mp4 data/agent-recording.mp4
echo "-> data/agent-recording.mp4"
