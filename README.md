# Subtext

Desktop app for downloading media, generating transcripts, and running local AI analysis.

## What It Does

- Download videos/audio from URLs (`yt-dlp`)
- Process local media files
- Generate transcripts with:
  - YouTube captions first (fast path, when available)
  - Whisper fallback
- Analyze transcripts locally with Ollama (summary, quotes, topics, sentiment)
- Export analysis to JSON/Markdown/HTML/PDF/TXT

## Requirements

- Windows 10/11 or macOS
- Python 3.11+
- `uv` installed: https://docs.astral.sh/uv/getting-started/installation/
- FFmpeg (`ffmpeg` and `ffprobe` on PATH): https://www.ffmpeg.org/download.html
- Optional but recommended:
  - Ollama for analysis
  - NVIDIA CUDA for faster Whisper on supported Windows/Linux systems

## Quick Start

**Easiest: double-click to launch (no terminal or venv needed)**

- **Windows:** double-click **win-run.bat**
- **macOS:** double-click **mac-run.command** (if it doesn’t run, in Terminal: `chmod +x "mac-run.command"`)

Choose **Desktop** (full app) or **Web** (browser UI for this PC and same Wi‑Fi devices). The launcher runs `uv sync` automatically on first run.

**From a terminal (optional):**

```bash
uv sync
uv run python run.py
# or
uv run python run_web.py
```

## FFmpeg Setup

Whisper transcription requires FFmpeg.

1. Install from: https://www.ffmpeg.org/download.html
2. Make sure both `ffmpeg` and `ffprobe` are available in your terminal `PATH`.
3. Restart Subtext after installation.

## First-Time Setup (AI Analysis)

1. Install Ollama: https://ollama.com/download/windows
2. Pull a model:
   ```bash
   ollama pull llama3.2
   ```
3. In Subtext:
   - Analysis tab -> `Refresh Models`
   - Select model
   - Click `Test Model`

## Recommended Workflow

1. Paste URL(s) or browse local files
2. Keep `YouTube Captions First` enabled for fast transcript generation on YouTube
3. Click `Start`
4. Review/edit transcript in Analysis tab
5. Run AI analysis and export results

## Optional CUDA Setup

If you want GPU acceleration for Whisper:

```bash
scripts\install_cuda.bat
```

Whisper device selection is automatic:
- `cuda` when available
- `mps` on supported Apple Silicon setups
- `cpu` fallback otherwise

## Project Structure

```text
Subtext/
  Start Subtext.bat      # Windows: double-click to launch (Desktop or Web)
  Start Subtext.command  # macOS: double-click to launch (Desktop or Web)
  run.py                 # Desktop app entry (use launcher or: uv run python run.py)
  run_web.py             # Web UI entry (use launcher or: uv run python run_web.py)
  src/
    config/        # paths and app configuration
    core/          # downloader, transcriber, analyzer, processor
    ui/            # window, tabs, workers, widgets, styles
  docs/
    ARCHITECTURE.md
  scripts/
    build_exe.py
    install_cuda.bat
  assets/          # generated files (videos/transcripts/analysis)
```

## Web UI (same network)

Double-click **Start Subtext** and choose **Web**, or run `uv run python run_web.py`. Then:

- On this PC: open **http://127.0.0.1:8765**
- From iPhone/tablet (same Wi‑Fi): open **http://\<this-PC-IP\>:8765**  
  (Find IP: `ipconfig` on Windows, `ip addr` or System Settings on Mac/Linux.)

Paste a video URL (YouTube, Instagram, X, TikTok, etc.) or upload a file, pick a Whisper model, then copy or download the transcript. Uses the same yt-dlp and Whisper setup as the desktop app.

## Useful Commands

- Run app: `uv run python run.py`
- Run web UI: `uv run python run_web.py`
- Build exe: `uv run python scripts/build_exe.py`
- Update deps: `uv sync --upgrade`
- Check installed models: `ollama list`

## Troubleshooting

- **`VIRTUAL_ENV does not match` (uv warning):** You don’t need to activate the venv. Use **Start Subtext** or run `uv run python run.py` (or `run_web.py`) from the project folder; `uv` uses the correct environment automatically.

- `Could not load model ...`:
  - Ensure Ollama is running and model is installed (`ollama list`)
  - In app click `Refresh Models`

- YouTube caption `429 Too Many Requests`:
  - Use browser cookies option
  - Retry later or switch network
  - App falls back to Whisper automatically

- High memory usage:
  - Use smaller Whisper model (`small.en` / `base.en`)
  - Use smaller Ollama models (`llama3.2:1b`, etc.)
  - Stop active Ollama models: `ollama ps` then `ollama stop <model>`

## License

MIT
