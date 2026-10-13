# CLAUDE.md

Guidance for Claude / AI coding agents working in this repository. Read this
first. For the longer contributor narrative see `AGENTS.md`; for product/design
framing see `docs/SPEC.md` and `docs/ARCHITECTURE.md`. When those disagree with
the code, the code wins — and update the docs to match.

## What Subtext Is

Subtext is **one local-first project with two companion modes** that share a
common core engine:

- **Private web service** (`run_web.py` → `src/web/`): a mobile-first FastAPI
  app for iPhone/Safari over Tailscale. Paste a URL or upload a file to
  transcribe, download original audio/video, run preset transcript analysis,
  and chat about a transcript with a local LLM (Ollama or LM Studio).
- **Desktop app** (`run.py` → `src/ui/`): a full PySide6 workstation with
  queued download/transcription, transcript review/editing, Ollama analysis,
  a chat tab, and multi-format export (JSON/Markdown/HTML/PDF/TXT).

Keep these modes coherent but distinct. Do **not** duplicate desktop-only
editing/export workflows into the web service, and do not implement web
features inside the Qt widgets, unless a task explicitly asks for parity.

**Default implementation target:** unless told otherwise, new feature work
targets the **web service** (`src/web/`) plus shared **`src/core/`**.

## Stack

- Python 3.11+ · `uv` for dependency management
- PySide6 (desktop UI) with QThread workers
- FastAPI + uvicorn (private web service), asyncio
- yt-dlp (download + YouTube captions), Whisper / optional faster-whisper
- Ollama and/or LM Studio for local LLM analysis + chat
- SQLite (chat thread persistence) · psutil (memory/system status)

## Repository Layout

```text
run.py / run_web.py        # launchers: desktop app / private web service
mac-run.command, win-run.bat
src/
  main.py                  # desktop entry point → src.ui.main_window.main()
  cli.py                   # CLI client for an ALREADY-RUNNING web service
  youtube_resolver.py      # shared crate title → YouTube resolver
  config/paths.py          # ProjectPaths — ALWAYS use for filesystem paths
  core/                    # shared business logic; NO direct UI updates
    input_processor.py     # parse/validate mixed URL + file input
    downloader.py          # media download + YouTube caption fetch/parse
    transcriber.py         # Whisper load/transcribe/save
    analyzer.py            # Ollama model mgmt + analysis presets (shared)
    processor.py           # orchestration + captions→Whisper fallback
  ui/                      # Desktop Qt UI ONLY
    main_window.py         # app shell, tab coordination, signal routing
    download_tab.py        # input/queue/progress/logs
    analysis_tab.py        # transcript review, model controls, analysis
    results_tab.py         # formatted results + export formats
    chat_tab.py            # local-LLM chat, optional transcript context
    styles.py
    widgets/multi_select_dropdown.py
    workers/               # QThread wrappers; communicate via signals only
      download_worker.py, analysis_worker.py, chat_worker.py
  web/                     # private FastAPI service + static client
    server.py              # all routes; warm Whisper; one heavy-work lock
    chat_store.py          # SQLite thread/message persistence (WAL)
    system_status.py       # memory snapshot + per-backend model inventory
    llm/lmstudio.py        # LM Studio streaming chat provider
    static/                # index.html, app.js, style.css, PWA manifest+icons
crates/                    # newline-delimited demo "crate" title lists
scripts/                   # install/start/maintenance helpers, LaunchAgent
docs/                      # ARCHITECTURE.md, SPEC.md (human-facing)
tests/                     # unittest suites (CLI, download modes, resolver)
```

## Commands

```bash
uv sync                       # install deps
uv sync --extra cuda          # add torch for CUDA
uv run python run.py          # desktop app
uv run python run_web.py      # private web service (127.0.0.1:8000)
curl http://127.0.0.1:8000/health
uv run python -m src.cli transcribe "<url-or-file>"
uv run python -m src.cli download|download-audio "<url>"
uv run python -m src.cli download-list [--audio-only] "<url-file>"
uv run python scripts/resolve_youtube_titles.py crates/morpher_demo_crate.txt
```

**Tests** use the stdlib `unittest` framework (no pytest dependency):

```bash
uv run python -m unittest discover -s tests -v
```

## Web Service API (`src/web/server.py`)

The service binds **localhost only** and is meant to sit behind Tailscale
Serve. Routes (all heavy work serialized behind a single async lock):

- `GET /`, `GET /health`
- `POST /transcribe`, `POST /api/transcribe`, `POST /transcribe/stream` —
  URL or uploaded-file transcription
- `POST /download-video`, `POST /download-audio` — attachment-style responses
- `POST /analyze`, `GET /analysis/meta` — preset transcript analysis + metadata
- `GET /chat/models`, `POST /chat/stream` — streaming local-LLM chat
- `GET/POST /chat/threads`, `GET /chat/threads/{id}/messages`,
  `DELETE /chat/threads/{id}` — SQLite-backed thread persistence
- `GET /system/status`, `POST /system/load`, `POST /system/unload` — memory +
  model inventory and explicit load/unload for the Models panel

### Key environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `SUBTEXT_SERVER_KEY` | — | shared secret; service returns 503 until set |
| `SUBTEXT_SERVER_HOST` / `SUBTEXT_SERVER_PORT` | `127.0.0.1` / `8000` | bind address |
| `SUBTEXT_MODEL` | `small.en` | Whisper model |
| `SUBTEXT_WHISPER_BACKEND` / `SUBTEXT_COMPUTE_TYPE` | `auto` / — | transcription backend |
| `SUBTEXT_ANALYSIS_MODEL` | `gemma3:4b` | analysis/chat model |
| `SUBTEXT_CHAT_PROVIDER` | `ollama` | `ollama` or `lmstudio` |
| `LMSTUDIO_HOST` | — | LM Studio host override |
| `SUBTEXT_CHAT_IDLE_SECONDS` / `SUBTEXT_TRANSCRIBE_IDLE_SECONDS` | `600` | idle unload windows |
| `SUBTEXT_ALLOWED_IPS` | — | optional IP allowlist (comma-separated) |
| `SUBTEXT_ANALYSIS_PREFERRED_MODELS` | — | bias the model selector |
| `SUBTEXT_YT_COOKIES` / `TRANSCRIPTAI_YT_BROWSER` | — | YouTube auth for captions |

CLI client honors `SUBTEXT_SERVER_URL` and `SUBTEXT_SERVER_KEY`.

## Architecture & Runtime Rules

- **Desktop:** UI updates happen on the UI thread only; long tasks run in
  `QThread` workers (`src/ui/workers/`) that each own an asyncio loop and talk
  back via Qt **signals only**. Signal routing lives in `main_window.py`
  (`DownloadTab.transcription_completed → AnalysisTab.load_transcript`;
  `AnalysisTab.analysis_completed → ResultsTab.load_results`).
- **Core never touches the UI.** Async I/O and integrations live in
  `src/core/` and `src/web/`, not in Qt widgets or browser JS.
- **Always use `ProjectPaths`** from `src/config/paths.py` for filesystem
  paths — never hardcode strings. Use `pathlib.Path`, not raw path strings.
- **Processing:** batch work is sequential by design (memory stability).
  YouTube prefers a captions-first fast path with retry/backoff; on failure or
  rate-limit (429) it falls back to media download + Whisper. Whisper device is
  auto-selected (`cuda → mps → cpu`) and requires `ffmpeg`/`ffprobe` on PATH.
- **Memory discipline:** desktop unloads Whisper after runs; Ollama uses
  `keep_alive="0s"`. The web service keeps Whisper warm but serializes all
  heavy work behind one lock and unloads idle chat/transcribe models.
- **Security model:** keep the web service localhost-only by default. Never
  reintroduce `0.0.0.0` / same-Wi-Fi / LAN assumptions. Prefer Tailscale.
  Never commit a real `SUBTEXT_SERVER_KEY` into tracked files (incl. the
  `scripts/*.plist` LaunchAgent template).

## Conventions

- Type hints required on public methods/functions; concise practical docstrings.
- Keep methods focused; prefer explicit names over abbreviations.
- Avoid bare `except:`; catch specific exceptions (the codebase uses
  `# noqa: BLE001` where a broad catch is deliberate).
- Prefer ASCII unless a file already uses non-ASCII.
- Keep dependency specs in `pyproject.toml`; default code paths stay simple.

## Common Feature Entry Points

- **Web feature:** `src/web/server.py` → `src/web/static/{index.html,app.js,style.css}`
  → `src/core/{downloader,transcriber,analyzer}.py` as needed.
- **Web chat/LLM:** `src/web/server.py` (`/chat/*`), `src/web/chat_store.py`,
  `src/web/llm/lmstudio.py`, `src/web/system_status.py`.
- **Desktop download/transcript option:** `widgets/multi_select_dropdown.py` →
  `download_tab.py` → `workers/download_worker.py` → `core/processor.py`.
- **Desktop AI analysis:** `core/analyzer.py` → `workers/analysis_worker.py` →
  `analysis_tab.py` → `results_tab.py`.
- **Export format:** `src/ui/results_tab.py`.

## When Behavior Changes, Update Docs

Keep these aligned when user-facing or contributor-facing behavior changes:
`README.md`, `docs/ARCHITECTURE.md`, `docs/SPEC.md`, `AGENTS.md`, and this
file. Docs must consistently describe the two companion modes, the web↔desktop
feature boundary, and the Tailscale-first private access model.

## Testing Checklist (validate what applies)

1. Desktop app launches: `uv run python run.py`
2. Web service launches + health: `uv run python run_web.py` then `curl .../health`
3. One URL transcription flow and one local-file flow
4. One web download-only flow (if download behavior changed)
5. One desktop analysis run (if Ollama code changed and Ollama is available)
6. One chat flow (if chat/LLM code changed)
7. One export path (if results/export behavior changed)
8. `uv run python -m unittest discover -s tests`

If something can't be tested locally, say so explicitly.

## Watch For (common drift)

- Launcher/README copy implying LAN / same-Wi-Fi web access.
- Docs overselling the web service as if it had full desktop editing/export.
- Helper scripts drifting from current LaunchAgent label
  (`com.subtext.private-web`), port, or log paths.
- Secrets accidentally landing in tracked plist/templates.
