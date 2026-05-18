#!/usr/bin/env zsh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

URL_FILE="${1:-$PROJECT_ROOT/crates/morpher_demo_crate.youtube.urls.txt}"
OUTPUT_FILE="${2:-$PROJECT_ROOT/crates/morpher_demo_crate.downloaded-files.txt}"

if [[ ! -f "$URL_FILE" ]]; then
  echo "URL file not found: $URL_FILE" >&2
  echo "Run: uv run python scripts/resolve_youtube_titles.py crates/morpher_demo_crate.txt" >&2
  exit 1
fi

if [[ -z "${SUBTEXT_SERVER_KEY:-}" ]]; then
  SUBTEXT_SERVER_KEY="$(
    launchctl print "gui/$(id -u)/com.subtext.private-web" 2>/dev/null \
      | awk -F'=> ' '/SUBTEXT_SERVER_KEY/ {gsub(/^ +| +$/, "", $2); print $2; exit}'
  )"
  export SUBTEXT_SERVER_KEY
fi

if [[ -z "${SUBTEXT_SERVER_KEY:-}" ]]; then
  echo "SUBTEXT_SERVER_KEY is not set and could not be read from launchd." >&2
  echo "Set it in this shell or confirm com.subtext.private-web is running." >&2
  exit 1
fi

cd "$PROJECT_ROOT"
mkdir -p "$(dirname "$OUTPUT_FILE")" Downloads

PENDING_URL_FILE="$(mktemp "${TMPDIR:-/tmp}/subtext-morpher-urls.XXXXXX")"
trap 'rm -f "$PENDING_URL_FILE"' EXIT

while IFS= read -r url; do
  [[ -z "$url" || "$url" == \#* ]] && continue

  video_id=""
  if [[ "$url" == *"watch?v="* ]]; then
    video_id="${url#*watch?v=}"
    video_id="${video_id%%&*}"
  elif [[ "$url" == *"youtu.be/"* ]]; then
    video_id="${url##*/}"
    video_id="${video_id%%\?*}"
  fi

  if [[ -n "$video_id" ]] && find Downloads -maxdepth 1 -type f -name "*${video_id}*" | grep -q .; then
    echo "Already downloaded: $url"
    continue
  fi

  echo "$url" >> "$PENDING_URL_FILE"
done < "$URL_FILE"

if [[ -s "$PENDING_URL_FILE" ]]; then
  uv run python -m src.cli download-list --audio-only "$PENDING_URL_FILE"
else
  echo "No new URLs to download."
fi

find "$PROJECT_ROOT/Downloads" -maxdepth 1 -type f -print | sort > "$OUTPUT_FILE"
echo "Saved downloaded file list to: $OUTPUT_FILE"
