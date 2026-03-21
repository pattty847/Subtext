# Subtext - Product Spec

## Core Vision

Subtext is a local-first media toolkit with two companion modes:

- a private web service for iPhone/browser download and transcription over Tailscale
- a desktop workstation for transcript review, Ollama analysis, and export

## Product Modes

### 1. Private Web Service

- Paste a supported media URL
- Download the original video to the phone
- Transcribe a URL or uploaded local media file
- Reach the service privately through Tailscale

### 2. Desktop App

- Queue URLs and local files
- Generate transcripts with captions-first + Whisper fallback
- Review and edit transcripts
- Run AI analysis locally with Ollama
- Export results in multiple formats

## Shared Core Engine (`src/core/`)

- **Downloader**: media retrieval and YouTube caption handling
- **Transcriber**: Whisper transcription
- **Analyzer**: Ollama-powered analysis for desktop workflows
- **Processor**: orchestration across download, transcription, and fallback paths

## Design Principles

- **Local-first**: keep media processing and AI workflows on the user’s machine
- **Private by default**: remote access goes through Tailscale, not open internet exposure
- **Fast enough to feel personal**: warm-model web service for repeat iPhone use
- **Clear mode boundaries**: remote convenience in web mode, deeper AI/export workflows in desktop mode

## Primary Workflows

### iPhone / Browser Workflow

1. Open the private Subtext URL through Tailscale
2. Paste a URL or upload a file
3. Transcribe media or download the original video

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
