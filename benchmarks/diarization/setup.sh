#!/bin/bash
# Install only inside this benchmark directory; no shell/profile changes.
set -euo pipefail
TASK_DIR="$(cd "$(dirname "$0")" && pwd)"
export UV_CACHE_DIR="${TMPDIR:-/tmp}/subtext-benchmark-uv"
uv venv "$TASK_DIR/.venv" --python 3.13 --allow-existing
uv pip sync --python "$TASK_DIR/.venv/bin/python" "$TASK_DIR/requirements-lock.txt"
ARCHIVE_URL='https://github.com/NVIDIA/NeMo-Speech.cpp/releases/download/v0.2.0/nemo-speech-0.2.0-macos-aarch64-metal.tar.gz'
TASK_TMP="$(mktemp -d)"
trap 'rm -rf "$TASK_TMP"' EXIT
curl -fsSL "$ARCHIVE_URL" -o "$TASK_TMP/runtime.tar.gz"
curl -fsSL "$ARCHIVE_URL.sha256" -o "$TASK_TMP/runtime.sha256"
"$TASK_DIR/.venv/bin/python" - "$TASK_TMP" <<'PY'
import hashlib
import sys
from pathlib import Path
p=Path(sys.argv[1])
assert hashlib.sha256((p/'runtime.tar.gz').read_bytes()).hexdigest()==(p/'runtime.sha256').read_text().split()[0], 'Runtime checksum mismatch'
PY
mkdir -p "$TASK_DIR/runtime"
tar -xzf "$TASK_TMP/runtime.tar.gz" -C "$TASK_DIR/runtime"
export NEMO_SPEECH_MODEL_DIR="$TASK_DIR/models"
"$TASK_DIR/runtime/nemo-speech-0.2.0-macos-aarch64-metal/bin/nemo-speech" pull nemotron-diar
"$TASK_DIR/.venv/bin/python" "$TASK_DIR/prepare.py"
