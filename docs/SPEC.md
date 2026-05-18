# Subtext - Product Spec

## Core Vision

Subtext is a local-first media toolkit with two companion modes:

- a private web service for iPhone/browser download, transcription, and preset transcript analysis over Tailscale
- a desktop workstation for transcript review, Ollama analysis, and export

It also includes a command-line client for programmatic transcribe/download access to the running private service.

## Product Modes

### 1. Private Web Service

- Paste a supported media URL
- Download the original video to the phone
- Transcribe a URL or uploaded local media file
- Run preset transcript analysis modes like caption ideas, hook rewrites, title packs, and custom prompts
- Reach the service privately through Tailscale

### 2. Desktop App

- Queue URLs and local files
- Generate transcripts with captions-first + Whisper fallback
- Review and edit transcripts
- Run AI analysis locally with Ollama
- Export results in multiple formats

### Command-Line Client

- Requires the private web service to already be running
- Transcribes a media URL or local media file without opening the browser UI
- Downloads a URL video without opening the browser UI
- Downloads a reviewed newline-delimited URL list sequentially
- Saves transcripts and downloaded media to `Subtext/Downloads`
- Uses the same shared-secret and localhost/Tailscale access model as the web UI

## Shared Core Engine (`src/core/`)

- **Downloader**: media retrieval and YouTube caption handling
- **Transcriber**: Whisper transcription
- **Analyzer**: Ollama-powered shared analysis for desktop workflows and web presets
- **Processor**: orchestration across download, transcription, and fallback paths

## Design Principles

- **Local-first**: keep media processing and AI workflows on the user’s machine
- **Private by default**: remote access goes through Tailscale, not open internet exposure
- **Fast enough to feel personal**: warm-model web service for repeat iPhone use
- **Clear mode boundaries**: remote convenience plus lightweight preset analysis in web mode, deeper editing/export workflows in desktop mode

## Primary Workflows

### iPhone / Browser Workflow

1. Open the private Subtext URL through Tailscale
2. Paste a URL or upload a file
3. Transcribe media or download the original video
4. Optionally run transcript analysis presets in-page

### Command-Line Workflow

1. Keep the private web service running locally or through Tailscale
2. Run `uv run python -m src.cli transcribe "<url-or-file>"`
3. Run `uv run python -m src.cli download "<url>"`
4. Or run `uv run python -m src.cli download-list "<url-file>"`
5. Collect output files from `Downloads/` in the Subtext project folder

### Demo Crate Resolution Workflow

1. Keep track titles in `crates/morpher_demo_crate.txt`
2. Run `uv run python scripts/resolve_youtube_titles.py crates/morpher_demo_crate.txt`
3. Review the generated TSV candidates before using the generated URL list

### Desktop Workflow

1. Paste or import media locally
2. Download and transcribe
3. Review the transcript
4. Run Ollama analysis
5. Export results

## Tech Choices

- **FastAPI**: private web service
- **PySide6**: desktop application
- **yt-dlp**: media download and extraction
- **Whisper / faster-whisper**: transcription
- **Ollama**: local AI analysis
