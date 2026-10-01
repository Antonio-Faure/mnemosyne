#!/usr/bin/env bash
# Verify the agent's traffic does NOT go through Tailscale.
#
# The agent's Chrome must browse with the machine's real (residential) IP.
# Tailscale is fine for admin access, but an *exit node* or accept-routes would
# silently route the agent's traffic through the tailnet. This script checks and
# returns non-zero on any problem.
set -euo pipefail

warn=0
note() { printf '%s\n' "$*"; }
bad() { printf 'WARN: %s\n' "$*"; warn=1; }

if command -v tailscale >/dev/null 2>&1; then
  prefs="$(tailscale debug prefs 2>/dev/null || true)"
  exit_ip="$(printf '%s' "$prefs" | grep -oP '"ExitNodeIP":\s*"\K[^"]*' || true)"
  route_all="$(printf '%s' "$prefs" | grep -oP '"RouteAll":\s*\K(true|false)' || true)"
  if [ -n "${exit_ip:-}" ]; then
    bad "Tailscale exit node is set ($exit_ip) — run: sudo tailscale set --exit-node="
  else
    note "OK: no Tailscale exit node"
  fi
  if [ "${route_all:-false}" = "true" ]; then
    bad "Tailscale accept-routes is ON — run: sudo tailscale set --accept-routes=false"
  else
    note "OK: Tailscale accept-routes off"
  fi
else
  note "OK: tailscale not installed"
fi

def_dev="$(ip route show default | awk '{print $5}' | head -1 || true)"
note "default route dev: ${def_dev:-unknown}"
[ "$def_dev" = "tailscale0" ] && bad "default route is tailscale0"

host_ip="$(curl -s --max-time 8 https://api.ipify.org || true)"
note "host egress IP: ${host_ip:-unknown}"

app="$(docker ps --format '{{.Names}}' 2>/dev/null | grep -i mnemosyne | head -1 || true)"
if [ -n "$app" ]; then
  cip="$(docker exec "$app" sh -c 'wget -qO- https://api.ipify.org' 2>/dev/null || true)"
  note "container egress IP: ${cip:-unknown}"
  if [ -n "$cip" ] && [ -n "$host_ip" ] && [ "$cip" != "$host_ip" ]; then
    bad "container egress ($cip) differs from host ($host_ip)"
  fi
else
  note "mnemosyne container not running (skipped container egress check)"
fi

if [ "$warn" -ne 0 ]; then
  note "RESULT: traffic may transit Tailscale — fix the warnings above."
  exit 1
fi
note "RESULT: egress is on the physical network, not Tailscale."
