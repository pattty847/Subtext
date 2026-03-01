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

# ── Build the plist from the template (via plistlib — safe for any key value) ─
TMP_PLIST="$(mktemp /tmp/com.subtext.web.XXXXXX.plist)"
python3 - "$PLIST_SRC" "$TMP_PLIST" "$UV_PATH" "$PROJECT_ROOT" "$API_KEY" <<'PYEOF'
import sys, plistlib, pathlib

src, dst, uv_path, project_root, api_key = sys.argv[1:]
with open(src, "rb") as f:
    pl = plistlib.load(f)

# Fix uv path and working directory
args = pl.get("ProgramArguments", [])
pl["ProgramArguments"] = [uv_path if a == "/usr/local/bin/uv" else a for a in args]
pl["WorkingDirectory"] = project_root

env = pl.setdefault("EnvironmentVariables", {})
if api_key:
    env["SUBTEXT_API_KEY"] = api_key
else:
    env.pop("SUBTEXT_API_KEY", None)

with open(dst, "wb") as f:
    plistlib.dump(pl, f)
PYEOF

if [[ -z "$API_KEY" ]]; then
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
