#!/usr/bin/env bash
# install_launchd.sh — one-shot installer for the Subtext launchd service
# Usage:  bash scripts/install_launchd.sh [API_KEY]
#
# What it does:
#   1. Detects the project root and uv binary paths automatically.
#   2. Substitutes them (plus your API key) into com.subtext.web.plist.
#   3. Copies the plist to ~/Library/LaunchAgents/ and loads it.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_SRC="$PROJECT_ROOT/com.subtext.web.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.subtext.web.plist"
API_KEY="${1:-}"

# ── Locate uv ────────────────────────────────────────────────────────────────
UV_PATH="$(command -v uv 2>/dev/null || true)"
if [[ -z "$UV_PATH" ]]; then
  echo "ERROR: 'uv' not found on PATH. Install it first:"
  echo "  curl -Lsf https://astral.sh/uv/install.sh | sh"
  exit 1
fi
echo "Found uv at: $UV_PATH"

# ── Build the plist from the template ────────────────────────────────────────
TMP_PLIST="$(mktemp /tmp/com.subtext.web.XXXXXX.plist)"
sed \
  -e "s|/usr/local/bin/uv|$UV_PATH|g" \
  -e "s|/YOUR_PROJECT_PATH/Subtext|$PROJECT_ROOT|g" \
  "$PLIST_SRC" > "$TMP_PLIST"

if [[ -n "$API_KEY" ]]; then
  # Replace the placeholder key value
  sed -i '' "s|YOUR_API_KEY|$API_KEY|g" "$TMP_PLIST"
else
  # Remove the SUBTEXT_API_KEY block entirely so the server runs open
  python3 - "$TMP_PLIST" <<'PYEOF'
import sys, plistlib, pathlib
path = pathlib.Path(sys.argv[1])
with open(path, "rb") as f:
    pl = plistlib.load(f)
pl.get("EnvironmentVariables", {}).pop("SUBTEXT_API_KEY", None)
with open(path, "wb") as f:
    plistlib.dump(pl, f)
PYEOF
  echo "No API key given — server will run without authentication."
fi

# ── Unload existing service if present ───────────────────────────────────────
if [[ -f "$PLIST_DST" ]]; then
  echo "Unloading existing service…"
  launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

# ── Install and load ──────────────────────────────────────────────────────────
cp "$TMP_PLIST" "$PLIST_DST"
rm "$TMP_PLIST"
launchctl load "$PLIST_DST"
echo ""
echo "Service installed and started."
echo "  Status : launchctl list | grep subtext"
echo "  Health : curl http://localhost:8765/health"
echo "  Logs   : tail -f /tmp/subtext-web.log"
echo "  Errors : tail -f /tmp/subtext-web.err"
echo ""

# ── Tailscale reminder ───────────────────────────────────────────────────────
TS_IP="$(tailscale ip -4 2>/dev/null || echo '<tailscale-ip>')"
echo "Tailscale endpoint: http://$TS_IP:8765/api/quick"
