#!/usr/bin/env bash
# Connect ONE discovered provider per run (dev agent researches it, opens a PR).
# Intended to be run daily by the mnemosyne-connect systemd user timer.
#
# Runs INSIDE the container: the bi-agent and its git worktree must share the
# container's paths. A host-side run registers worktrees the container sees as
# broken — and its `git worktree prune` drops the container's registrations
# mid-session (a real crash: "not a git repository: /repo/.git/worktrees/...").
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p data
{
    echo "=== $(date -Is) connect-next ==="
    docker compose exec -T mnemosyne mnemosyne connect-next
} >> data/connect.log 2>&1
