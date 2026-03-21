#!/usr/bin/env bash
# install_launchd.sh — install/update the Subtext private web service LaunchAgent
# Usage:
#   bash scripts/install_launchd.sh [SUBTEXT_SERVER_KEY]
#
# What it does:
#   1. Loads scripts/com.subtext.private-web.plist as a template.
#   2. Rewrites project-specific paths and the shared secret.
#   3. Installs the LaunchAgent to ~/Library/LaunchAgents/.
#   4. Bootstraps and kickstarts the service for the current macOS user session.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PLIST_SRC="$PROJECT_ROOT/scripts/com.subtext.private-web.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.subtext.private-web.plist"
SERVER_KEY="${1:-}"
USER_DOMAIN="gui/$(id -u)"

mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$PROJECT_ROOT/assets/logs"

if [[ ! -f "$PLIST_SRC" ]]; then
  echo "ERROR: template not found: $PLIST_SRC"
  exit 1
fi

TMP_PLIST="$(mktemp /tmp/com.subtext.private-web.XXXXXX.plist)"
python3 - "$PLIST_SRC" "$TMP_PLIST" "$PROJECT_ROOT" "$SERVER_KEY" <<'PYEOF'
import plistlib
import sys
from pathlib import Path

src, dst, project_root, server_key = sys.argv[1:]
project_root = Path(project_root)

with open(src, "rb") as handle:
    pl = plistlib.load(handle)

program_args = pl.get("ProgramArguments", [])
if len(program_args) >= 2:
    program_args[1] = str(project_root / "scripts" / "start_private_web.sh")
pl["ProgramArguments"] = program_args
pl["WorkingDirectory"] = str(project_root)
pl["StandardOutPath"] = str(project_root / "assets" / "logs" / "launchd.out.log")
pl["StandardErrorPath"] = str(project_root / "assets" / "logs" / "launchd.err.log")

env = pl.setdefault("EnvironmentVariables", {})
env["SUBTEXT_SERVER_HOST"] = "127.0.0.1"
env["SUBTEXT_SERVER_PORT"] = "8000"
if server_key:
    env["SUBTEXT_SERVER_KEY"] = server_key

with open(dst, "wb") as handle:
    plistlib.dump(pl, handle)
PYEOF

cp "$TMP_PLIST" "$PLIST_DST"
rm "$TMP_PLIST"

launchctl bootout "$USER_DOMAIN" "$PLIST_DST" 2>/dev/null || true
launchctl bootstrap "$USER_DOMAIN" "$PLIST_DST"
launchctl kickstart -k "$USER_DOMAIN/com.subtext.private-web"

echo ""
echo "Subtext private web service LaunchAgent installed."
echo "  LaunchAgent : $PLIST_DST"
echo "  Health      : curl http://127.0.0.1:8000/health"
echo "  Logs        : tail -f \"$PROJECT_ROOT/assets/logs/private_web.log\""
echo "  Stdout      : tail -f \"$PROJECT_ROOT/assets/logs/launchd.out.log\""
echo "  Stderr      : tail -f \"$PROJECT_ROOT/assets/logs/launchd.err.log\""
echo ""
echo "If you want iPhone access, publish it privately with:"
echo "  tailscale serve --bg 8000 http://127.0.0.1:8000"
