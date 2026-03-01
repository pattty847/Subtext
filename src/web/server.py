"""
Web server for Subtext: URL or file upload -> download (yt-dlp) -> transcribe (Whisper).
Reuses core processor; reachable on 0.0.0.0 for home network (e.g. from phone).

Tailscale API key auth:
  Set SUBTEXT_API_KEY in the environment (or in the launchd plist).
  Clients must send:  Authorization: Bearer <key>
  If the env var is unset the server runs open (safe behind Tailscale).
"""
import asyncio
import os
import secrets
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from src.config.paths import ProjectPaths
from src.core.processor import UnifiedProcessor, ProcessingItem
from src.core.downloader import DownloadProgress
from src.core.transcriber import TranscriptionProgress

# Ensure assets exist
ProjectPaths.initialize()

app = FastAPI(title="Subtext Web", description="Transcribe video from URL or upload")
JOBS: dict[str, dict[str, Any]] = {}

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
_API_KEY: str = os.environ.get("SUBTEXT_API_KEY", "")


def _require_auth(authorization: str = Header(default="")) -> None:
    """Dependency: validate Bearer token when SUBTEXT_API_KEY is configured."""
    if not _API_KEY:
        return  # no key set → open (safe behind Tailscale ACLs)
    if not secrets.compare_digest(authorization, f"Bearer {_API_KEY}"):
        raise HTTPException(status_code=401, detail="Invalid or missing API key.")

WHISPER_MODELS = ["tiny.en", "base.en", "small.en", "medium.en", "large-v3"]


def _update_job(job_id: str, **kwargs: Any) -> None:
    if job_id in JOBS:
        JOBS[job_id].update(kwargs)


@app.post("/api/transcribe")
async def create_transcribe_job(
    model: str = Form("small.en"),
    url: Optional[str] = Form(None),
    file: Optional[UploadFile] = None,
) -> dict[str, str]:
    """Start a transcription job. Provide either `url` or `file`, not both."""
    if not url and not file:
        raise HTTPException(400, "Provide either a URL or an uploaded file.")
    if url and file:
        raise HTTPException(400, "Provide either a URL or a file, not both.")

    model = (model or "small.en").strip()
    if model not in WHISPER_MODELS:
        model = "small.en"

    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "status": "pending",
        "progress": 0.0,
        "message": "Starting…",
        "transcript": None,
        "error": None,
    }

    if url:
        input_text = url.strip()
    else:
        # Save uploaded file to assets/videos with a unique name
        assert file is not None
        suffix = Path(file.filename or "upload").suffix or ".mp4"
        safe_name = f"web_upload_{job_id}{suffix}"
        dest = ProjectPaths.VIDEOS_DIR / safe_name
        content = await file.read()
        dest.write_bytes(content)
        input_text = str(dest)

    asyncio.create_task(_run_job(job_id, input_text, model))
    return {"job_id": job_id}


async def _run_job(job_id: str, input_text: str, model: str) -> None:
    _update_job(job_id, status="running", message="Processing…")

    def progress_cb(msg: str) -> None:
        _update_job(job_id, message=msg)

    def download_cb(dp: DownloadProgress) -> None:
        _update_job(job_id, progress=dp.percent, message=f"Downloading… {dp.percent:.1f}%")

    def transcription_cb(tp: TranscriptionProgress) -> None:
        _update_job(job_id, progress=tp.percent, message=tp.message)

    processor = UnifiedProcessor(
        model=model,
        download_only=False,
        keep_video=False,
        copy_files=False,
        youtube_captions_first=True,
        use_browser_cookies=True,
    )
    try:
        results = await processor.process_mixed_input(
            input_text,
            progress_callback=progress_cb,
            download_progress_callback=download_cb,
            transcription_progress_callback=transcription_cb,
        )
        item: Optional[ProcessingItem] = results[0] if results else None
        if item and item.status == "completed" and item.transcript_path and item.transcript_path.exists():
            transcript = item.transcript_path.read_text(encoding="utf-8")
            _update_job(
                job_id,
                status="completed",
                progress=100.0,
                message="Done",
                transcript=transcript,
            )
        elif item and item.status == "error" and item.error_message:
            _update_job(job_id, status="error", error=item.error_message)
        else:
            _update_job(job_id, status="error", error="No transcript produced.")
    except Exception as e:
        _update_job(job_id, status="error", error=str(e))


@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str) -> dict[str, Any]:
    """Get current job status and result."""
    if job_id not in JOBS:
        raise HTTPException(404, "Job not found.")
    return JOBS[job_id]


# ---------------------------------------------------------------------------
# /api/quick  –  synchronous endpoint designed for Shortcuts / CLI callers
# ---------------------------------------------------------------------------

class QuickRequest(BaseModel):
    url: str
    model: str = "small.en"
    plain_text: bool = False  # true → return bare text instead of JSON


async def _run_quick(url: str, model: str) -> str:
    """Run the full pipeline and return the transcript text, or raise on error."""
    model = m if (m := model.strip()) in WHISPER_MODELS else "small.en"
    processor = UnifiedProcessor(
        model=model,
        download_only=False,
        keep_video=False,
        copy_files=False,
        youtube_captions_first=True,
        use_browser_cookies=True,
    )
    results = await processor.process_mixed_input(url.strip())
    item: Optional[ProcessingItem] = results[0] if results else None
    if item and item.status == "completed" and item.transcript_path and item.transcript_path.exists():
        return item.transcript_path.read_text(encoding="utf-8")
    error = (item.error_message if item else None) or "No transcript produced."
    raise HTTPException(status_code=500, detail=error)


@app.post("/api/quick")
async def quick_transcribe_post(
    body: QuickRequest,
    _: None = Depends(_require_auth),
) -> Response:
    """
    Synchronous transcription — returns the transcript directly (no polling).

    POST /api/quick
    Headers: Authorization: Bearer <SUBTEXT_API_KEY>
    Body (JSON): {"url": "https://...", "model": "small.en", "plain_text": false}
    """
    transcript = await _run_quick(body.url, body.model)
    if body.plain_text:
        return PlainTextResponse(transcript)
    return JSONResponse({"transcript": transcript, "url": body.url, "model": body.model})


@app.get("/api/quick")
async def quick_transcribe_get(
    url: str = Query(..., description="Video URL to transcribe"),
    model: str = Query(default="small.en"),
    plain_text: bool = Query(default=False, description="Return bare text instead of JSON"),
    _: None = Depends(_require_auth),
) -> Response:
    """
    Synchronous transcription via GET — convenient for curl and Shortcuts URL actions.

    GET /api/quick?url=https://...&model=small.en
    Headers: Authorization: Bearer <SUBTEXT_API_KEY>
    """
    transcript = await _run_quick(url, model)
    if plain_text:
        return PlainTextResponse(transcript)
    return JSONResponse({"transcript": transcript, "url": url, "model": model})


# Static files (HTML, CSS, JS)
STATIC_DIR = Path(__file__).parent / "static"
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    index_html = STATIC_DIR / "index.html"
    if not index_html.exists():
        raise HTTPException(404, "Static files not found. Run from project root.")
    return HTMLResponse(content=index_html.read_text(encoding="utf-8"))


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
