#!/usr/bin/env bash
# Connect ONE discovered provider per run (dev agent researches it, opens a PR).
# Intended to be run daily by the mnemosyne-connect systemd user timer.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
{
    echo "=== $(date -Is) connect-next ==="
    .venv/bin/mnemosyne connect-next
} >> data/connect.log 2>&1
