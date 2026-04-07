# Subtext

Subtext is one local-first project with two companion modes: a private iPhone-friendly web service for downloading, transcribing, and running lightweight transcript analysis over Tailscale, and a full desktop app for transcript review, Ollama analysis, and exports.

## What Subtext Is

Subtext helps you do two related jobs without sending your media to random web tools:

- **Private web service**: use Safari on your iPhone to paste a URL, upload a file, transcribe media, run optional preset transcript analysis, or download the original video.
- **Desktop app**: work locally on your Mac or PC with transcript review, AI analysis, and export tools.

## Choose Your Mode

### Private iPhone Service

Best when you want an always-on personal media tool you can reach from your phone.

- Paste a supported URL and transcribe it
- Run meme-focused transcript analysis presets from the resulting transcript
- Paste a supported URL and download the original video
- Upload a local audio/video file from Safari
- Reach it privately through Tailscale

### Desktop AI Analysis

Best when you want the full Subtext workflow on one computer.

- Download or import media locally
- Generate transcripts with captions-first + Whisper fallback
- Review and edit transcripts
- Run Ollama analysis and export results

Important: the private web service now supports preset transcript analysis, but it still does **not** include the full PySide desktop transcript editing or export workflow.

## Fastest Setup: Mac + iPhone

This is the easiest path if your goal is a private always-on service for your phone.

### 1) Install prerequisites

- Install `uv`: https://docs.astral.sh/uv/getting-started/installation/
- Install FFmpeg: https://www.ffmpeg.org/download.html
- Install Tailscale on your Mac and iPhone, then sign in on both devices

Make sure `ffmpeg` and `ffprobe` are available in your terminal `PATH`.

### 2) Install Subtext dependencies

```bash
uv sync
```

Optional faster backend:

```bash
uv sync --extra faster
```

### 3) Set the private web service key

```bash
export SUBTEXT_SERVER_KEY="$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')"
export SUBTEXT_SERVER_HOST=127.0.0.1
export SUBTEXT_SERVER_PORT=8000
export SUBTEXT_MODEL=small.en
export SUBTEXT_ANALYSIS_MODEL=gemma3:4b
```

`SUBTEXT_SERVER_KEY` is the shared secret your phone sends to the service.

### 4) Start the private web service

```bash
uv run python run_web.py
```

Check that it is alive locally:

```bash
curl http://127.0.0.1:8000/health
```

### 5) Publish it privately through Tailscale (recommended)

Subtext listens on **localhost only** (`127.0.0.1:8000`). Tailscale **Serve** exposes that port to your Tailnet with HTTPS and access control — this is the supported “phone from anywhere” path. It is **not** a public-internet deployment; only devices on your Tailnet can reach it.

```bash
tailscale serve --bg 8000 http://127.0.0.1:8000
```

Then get the Tailnet URL:

```bash
tailscale serve status
```

Open the listed Tailnet URL in Safari on your iPhone and enter your `SUBTEXT_SERVER_KEY`.

There is no separate “public” plist or LAN-focused LaunchAgent in this repo on purpose: binding to `0.0.0.0` or same-Wi-Fi URLs is not the default security model.

### 6) Use it from your phone

From Safari on iPhone you can:

- paste a supported media URL and tap `Transcribe`
- run `Caption Ideas`, `Hook Rewrites`, `Title Pack`, or a custom prompt on the transcript with a selected humor style
- paste a supported media URL and tap `Download Video Only`
- upload a local audio/video file and transcribe it

### Optional: keep the web service always online on macOS (LaunchAgent)

Use **one** tracked template — everything else should match it:

| What | Path |
|------|------|
| LaunchAgent plist (template; edit secret after copy, or use the installer) | `scripts/com.subtext.private-web.plist` |
| Installer (rewrites paths, optional key, installs to `~/Library/LaunchAgents/`) | `scripts/install_launchd.sh` |
| Wrapper the plist runs | `scripts/start_private_web.sh` |

Install (from the repo root; pass your key, or set `SUBTEXT_SERVER_KEY` in the generated plist afterward):

```bash
bash scripts/install_launchd.sh "$SUBTEXT_SERVER_KEY"
```

The LaunchAgent only starts **Subtext on localhost** at login. It does **not** run `tailscale serve` for you — run step 5 once (or add your own automation) so your phone still uses the Tailnet URL from `tailscale serve status`.

Important:

- Label in the template: `com.subtext.private-web` (restart with `launchctl kickstart -k gui/$(id -u)/com.subtext.private-web`).
- Subtext stays bound to `127.0.0.1:8000` by default.
- Tailscale proxies traffic privately; the service is not exposed on `0.0.0.0`.
- `http://<tailscale-ip>:8000` is not the recommended access path. Use the Tailnet URL from `tailscale serve status`.

## Desktop AI Analysis Setup

Use this mode when you want the full local review and AI workflow.

### 1) Start the desktop app

```bash
uv run python run.py
```

Or use the launchers:

- macOS: `./mac-run.command`
- Windows: `win-run.bat`

### 2) Install Ollama for analysis

1. Install Ollama: https://ollama.com/download
2. Pull a model:
   ```bash
   ollama pull gemma3:4b
   ```
3. In the Desktop app:
   - open the `AI Analysis` tab
   - click `Refresh Models`
   - select a model
   - click `Test Model`

### 3) Run the full workflow

1. Paste URL(s) or browse local files
2. Start download/transcription
3. Review the transcript
4. Run AI analysis
5. Export JSON, Markdown, HTML, PDF, or TXT

## Capabilities By Mode

### Private Web Service

- URL transcription
- Local file transcription
- URL video download
- iPhone/Safari access over Tailscale
- Warm-loaded Whisper model for faster repeat requests
- On-demand transcript analysis presets with Ollama

### Desktop App

- URL + file queueing
- Transcript review/editing
- Ollama analysis
- Results tab and exports
- Richer local workflow controls

## If You Just Want It Working Again

Private web service:

```bash
cd /Users/copeharder/Programming/Subtext
uv run python run_web.py
tailscale serve status
```

LaunchAgent-managed restart:

```bash
launchctl kickstart -k gui/$(id -u)/com.subtext.private-web
curl http://127.0.0.1:8000/health
```

Desktop app:

```bash
cd /Users/copeharder/Programming/Subtext
uv run python run.py
```

## Useful Commands

- Run Desktop app: `uv run python run.py`
- Run private web service: `uv run python run_web.py`
- Install faster backend: `uv sync --extra faster`
- Update dependencies: `uv sync --upgrade`
- Check Ollama models: `ollama list`
- Check Tailscale Serve status: `tailscale serve status`
- Local health check: `curl http://127.0.0.1:8000/health`

## Performance Notes

- `small.en` is the default model because it is a good speed/quality tradeoff for an always-on Apple Silicon service.
- `gemma3:4b` is the default transcript-analysis model for the private web service and desktop analysis.
- If installed, `faster-whisper` can be enabled through `uv sync --extra faster`.
- Whisper device selection is automatic:
  - `cuda` when available
  - `mps` on supported Apple Silicon setups
  - `cpu` otherwise

## Troubleshooting

- **`VIRTUAL_ENV does not match` warning:**
  Use `uv run ...` from the project folder. You do not need to activate a virtualenv manually.

- **FFmpeg missing:**
  Install FFmpeg and make sure both `ffmpeg` and `ffprobe` are on your `PATH`.

- **Private service returns `503 Access control is not configured`:**
  Set `SUBTEXT_SERVER_KEY` and restart the service.

- **Phone cannot connect:**
  Confirm the web service is running locally, then run `tailscale serve status` and open the listed Tailnet URL.

- **YouTube caption rate limiting (`429`):**
  Retry later, provide cookies if needed, or let Subtext fall back to Whisper.

- **High memory usage:**
  Use a smaller Whisper model such as `small.en` or `base.en`, and use smaller Ollama models like `gemma3:4b` for transcript analysis.

## License

MIT
