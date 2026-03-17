# AGENTS.md - Subtext Contributor Guide

This file is the fast context guide for coding agents and contributors.

## Project Goals

- Keep the app fast and simple for non-technical users.
- Prefer local-first processing (privacy + low cloud dependency).
- Preserve UI responsiveness during heavy work.
- Favor clear error messages and safe fallbacks.

## Stack

- Python 3.11+
- PySide6 UI
- AsyncIO + QThread workers
- yt-dlp (download + captions)
- Whisper (transcription)
- Ollama (local LLM analysis)
- `uv` for dependency management

## Code Boundaries

- `src/ui/`: Qt UI only (widgets, tabs, signal wiring)
- `src/ui/workers/`: QThread wrappers for async core calls
- `src/core/`: business logic and integrations (no direct UI updates)
- `src/config/`: path/config constants
- `scripts/`: maintenance/build helper scripts
- `docs/`: human-facing technical docs

Do not place heavy business logic directly in UI tab classes.

## Runtime Rules

1. UI updates must happen in the UI thread.
2. Long tasks must run in workers.
3. Workers should communicate with signals only.
4. Async I/O belongs in core modules.
5. Always use `ProjectPaths` from `src/config/paths.py`.

## Current Processing Behavior

- Input can mix URLs and local file paths.
- YouTube URLs can use captions-first fast path.
- If captions fail/unavailable/rate-limited, fallback to Whisper.
- Batch is sequential by design (memory stability).
- Whisper model resources are unloaded after processing.
- Ollama calls use low-memory behavior (model unload after requests).

## Conventions

- Type hints required on public methods/functions.
- Keep methods focused and short.
- Prefer explicit names over abbreviations.
- Keep docstrings concise and practical.
- Use `pathlib.Path`, not raw path strings.
- Avoid broad `except:`; catch specific exceptions where possible.

## Dependency and Tooling

- Use `uv sync` to install.
- Use `uv run ...` to execute scripts.
- Keep dependency specs in `pyproject.toml`.

## Documentation Expectations

When behavior changes, update:

1. `README.md` (user-facing setup/use)
2. `docs/ARCHITECTURE.md` (technical flow/components)
3. This file when workflow/conventions shift

## Testing Expectations

Before finalizing changes, validate at least:

1. App launches (`uv run python run.py`)
2. One URL processing flow
3. One local file flow
4. One analysis run (if Ollama available)
5. Export path still works

If something cannot be tested locally, clearly note it.

## Safe Defaults

- Prefer memory-safe behavior over maximum throughput.
- Prefer fallback behavior over hard failure.
- Prefer clear status/log messages over silent retries.

## Web UI

- `run_web.py`: starts the private FastAPI service on `127.0.0.1:8000` by default
- `src/web/server.py`: private API + static serving; warm-loaded transcription model, request logging, access-control middleware
- `src/web/static/`: mobile-friendly single-page UI (audio upload, optional recording, transcript display)

## Common Feature Entry Points

- New download/transcript option:
  - `src/ui/widgets/multi_select_dropdown.py`
  - `src/ui/download_tab.py`
  - `src/ui/workers/download_worker.py`
  - `src/core/processor.py`

- New analysis feature:
  - `src/core/analyzer.py`
  - `src/ui/workers/analysis_worker.py`
  - `src/ui/analysis_tab.py`
  - `src/ui/results_tab.py`
