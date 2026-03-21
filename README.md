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

Choose **Desktop** (full app) or **Web** (private transcription service). The launcher runs `uv sync` automatically on first run.

**From a terminal (optional):**

```bash
uv sync
uv run python run.py
# or
uv run python run_web.py
```

Optional faster backend:

```bash
uv sync --extra faster
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

## Private Web Service (Tailscale + API Key)

You can run Subtext as an always-online private service on your Mac and securely use it from your phone.

### 1) Set service environment variables

```bash
export SUBTEXT_SERVER_HOST=127.0.0.1
export SUBTEXT_SERVER_PORT=8000
export SUBTEXT_MODEL=small.en
export SUBTEXT_SERVER_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
```

`SUBTEXT_SERVER_KEY` is your API key / shared secret for remote access.

### 2) Start the web service

```bash
uv run python run_web.py
```

### 3) Verify locally

```bash
curl http://127.0.0.1:8000/health
```

### 4) Publish privately through Tailscale (no public port)

```bash
tailscale serve --bg 8000 http://127.0.0.1:8000
```

### 5) Open from your phone

Run:

```bash
tailscale serve status
```

Open the listed Tailnet URL in Safari (or any browser) on your iPhone, then enter your `SUBTEXT_SERVER_KEY` when prompted.
From there you can:
- paste a supported media URL and transcribe it
- paste a supported media URL and use `Download Video Only` to save the highest-quality video Safari will accept
- upload a local audio/video file for transcription

### Optional: keep it always online on macOS

Use the included LaunchAgent (`com.subtext.web.plist`) to auto-start Subtext on boot/login so your phone can connect any time.

Important:
- `http://<tailscale-ip>:8000` requires binding directly to the tailnet address, which conflicts with localhost-only hardening.
- Recommended setup: keep Subtext bound to `127.0.0.1` and let Tailscale proxy private traffic in.

## Useful Commands

- Run app: `uv run python run.py`
- Run private web service: `uv run python run_web.py`
- Build exe: `uv run python scripts/build_exe.py`
- Update deps: `uv sync --upgrade`
- Check installed models: `ollama list`
- Check Tailscale Serve status: `tailscale serve status`

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

- Private service returns `503 Access control is not configured`:
  - Set `SUBTEXT_SERVER_KEY`
  - Or set `SUBTEXT_ALLOWED_IPS` / `SUBTEXT_ALLOW_TAILSCALE_IPS`
  - Restart the service after changing environment variables

## License

MIT
