"""
Private web service for Subtext.

The service is designed to run on localhost and be exposed privately through
Tailscale. Audio uploads are transcribed synchronously with a warm model.
"""
from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import mimetypes
import os
import secrets
import time
import uuid
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, AsyncGenerator, List, Optional

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from src.config.paths import ProjectPaths
from src.core.analyzer import (
    DEFAULT_ANALYSIS_MODEL,
    DEFAULT_HUMOR_STYLE,
    DEFAULT_PRESET,
    MODEL_FALLBACKS,
    OllamaAnalyzer,
)
from src.core.downloader import UniversalDownloader
from src.core.transcriber import WhisperTranscriber

ProjectPaths.initialize()

LOGGER = logging.getLogger("subtext.private_service")
TAILSCALE_NETWORK = ipaddress.ip_network("100.64.0.0/10")
STATIC_DIR = Path(__file__).parent / "static"
ALLOWED_EXTENSIONS = {
    ".wav",
    ".m4a",
    ".mp3",
    ".mp4",
    ".aac",
    ".flac",
    ".ogg",
    ".opus",
    ".webm",
}
WHISPER_MODELS = ["tiny.en", "base.en", "small.en", "medium.en", "large-v3"]


def _sse_event(event: str, payload: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _env_flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class ServiceConfig:
    """Runtime configuration sourced from environment variables."""

    def __init__(self) -> None:
        self.model_name = os.getenv("SUBTEXT_MODEL", "small.en").strip() or "small.en"
        if self.model_name not in WHISPER_MODELS:
            self.model_name = "small.en"

        self.backend = os.getenv("SUBTEXT_WHISPER_BACKEND", "auto").strip() or "auto"
        self.compute_type = os.getenv("SUBTEXT_COMPUTE_TYPE", "").strip() or None
        self.analysis_model = os.getenv("SUBTEXT_ANALYSIS_MODEL", DEFAULT_ANALYSIS_MODEL).strip() or DEFAULT_ANALYSIS_MODEL
        self.server_key = os.getenv("SUBTEXT_SERVER_KEY", "").strip()
        self.allow_tailscale_ips = _env_flag("SUBTEXT_ALLOW_TAILSCALE_IPS", False)
        # ── CopeNet integration ───────────────────────────────────────────────
        # Set COPENET_API_URL to your CopeNet instance (e.g. http://localhost:7860)
        # to proxy /chat/stream through it instead of calling Ollama directly.
        # Leave blank to use Ollama as a direct fallback.
        self.copenet_api_url = os.getenv("COPENET_API_URL", "").strip().rstrip("/")
        self.allowed_ips = {
            entry.strip()
            for entry in os.getenv("SUBTEXT_ALLOWED_IPS", "").split(",")
            if entry.strip()
        }
        self.trust_proxy_headers = _env_flag("SUBTEXT_TRUST_PROXY_HEADERS", False)
        preferred_models_env = os.getenv("SUBTEXT_ANALYSIS_PREFERRED_MODELS", "").strip()
        if preferred_models_env:
            self.preferred_analysis_models = [
                value.strip() for value in preferred_models_env.split(",") if value.strip()
            ]
        else:
            self.preferred_analysis_models = MODEL_FALLBACKS.copy()


class AnalyzeRequest(BaseModel):
    transcript: str = Field(min_length=1)
    preset: str = Field(default=DEFAULT_PRESET)
    humor_style: str = Field(default=DEFAULT_HUMOR_STYLE)
    model: Optional[str] = Field(default=None)
    custom_prompt: str = Field(default="")


class ChatMsg(BaseModel):
    role: str   # "user" | "assistant" | "system"
    content: str


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    history: List[ChatMsg] = Field(default_factory=list)
    model: Optional[str] = Field(default=None)
    # Optional transcript injected as a system-level context message.
    # When CopeNet is wired up this passes through as-is; CopeNet owns
    # session memory, so history may be empty and context carries state.
    transcript_context: Optional[str] = Field(default=None)


class AnalysisMetaResponse(BaseModel):
    default_model: str
    preferred_models: List[str]
    available_models: List[str]
    presets: List[dict[str, str]]
    humor_styles: List[dict[str, str]]


class PrivateTranscriptionService:
    """Warm-model transcription service with a single-flight queue."""

    def __init__(self, config: ServiceConfig) -> None:
        self.config = config
        self.downloader = UniversalDownloader()
        self.transcriber = WhisperTranscriber(
            model_name=config.model_name,
            backend=config.backend,
            compute_type=config.compute_type,
        )
        self.analyzer = OllamaAnalyzer(config.analysis_model)
        self._lock = asyncio.Lock()

    async def startup(self) -> None:
        def progress_callback(progress) -> None:
            LOGGER.info("startup: %s", progress.message)

        await self.transcriber.load_model(progress_callback=progress_callback)
        LOGGER.info(
            "whisper_ready model=%s backend=%s device=%s compute_type=%s",
            self.transcriber.model_name,
            self.transcriber.backend,
            self.transcriber.device,
            self.transcriber.compute_type,
        )

    async def shutdown(self) -> None:
        self.transcriber.unload_model()
        LOGGER.info("whisper_unloaded")

    async def transcribe_upload(self, file: UploadFile) -> dict[str, float | str]:
        suffix = Path(file.filename or "upload.wav").suffix.lower()
        if suffix not in ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Use wav, m4a, mp3, mp4, aac, flac, ogg, opus, or webm.",
            )

        temp_path = ProjectPaths.RUNTIME_DIR / f"upload_{uuid.uuid4().hex}{suffix}"
        started_at = time.perf_counter()

        try:
            with temp_path.open("wb") as handle:
                while True:
                    chunk = await file.read(1024 * 1024)
                    if not chunk:
                        break
                    handle.write(chunk)

            async with self._lock:
                duration = self.transcriber.get_audio_duration(temp_path)
                text = await self.transcriber.transcribe(temp_path)

            latency = time.perf_counter() - started_at
            return {
                "text": text,
                "duration": round(duration, 3),
                "latency": round(latency, 3),
            }
        finally:
            await file.close()
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                LOGGER.warning("cleanup_failed path=%s", temp_path)

    async def transcribe_url(self, url: str) -> dict[str, float | str]:
        cleaned_url = url.strip()
        if not cleaned_url:
            raise HTTPException(status_code=400, detail="URL is required.")

        started_at = time.perf_counter()
        downloaded_path: Optional[Path] = None
        try:
            async with self._lock:
                downloaded_path = await self.downloader.download(cleaned_url)
                duration = self.transcriber.get_audio_duration(downloaded_path)
                text = await self.transcriber.transcribe(downloaded_path)

            latency = time.perf_counter() - started_at
            return {
                "text": text,
                "duration": round(duration, 3),
                "latency": round(latency, 3),
            }
        finally:
            if downloaded_path is not None:
                try:
                    downloaded_path.unlink(missing_ok=True)
                except Exception:
                    LOGGER.warning("cleanup_failed path=%s", downloaded_path)

    async def list_analysis_models(self) -> List[str]:
        return await self.analyzer.list_available_models()

    async def stream_chat(
        self,
        messages: List[dict],
        model: str,
    ) -> AsyncGenerator[str, None]:
        """
        Stream chat tokens from Ollama via a background thread.

        Yields raw token strings. Raises RuntimeError on model failure.
        When COPENET_API_URL is configured this method will be swapped out
        for a CopeNet proxy call — the yield contract stays the same.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        def _blocking_stream() -> None:
            try:
                for chunk in self.analyzer.client.chat(
                    model=model,
                    messages=messages,
                    stream=True,
                ):
                    content = OllamaAnalyzer._extract_chat_content(chunk)
                    if content:
                        loop.call_soon_threadsafe(queue.put_nowait, ("token", content))
                loop.call_soon_threadsafe(queue.put_nowait, ("done", ""))
            except Exception as exc:  # noqa: BLE001
                loop.call_soon_threadsafe(queue.put_nowait, ("error", str(exc)))

        future = loop.run_in_executor(None, _blocking_stream)

        while True:
            kind, data = await queue.get()
            if kind == "token":
                yield data
            elif kind == "done":
                await future
                return
            else:
                await asyncio.gather(future, return_exceptions=True)
                raise RuntimeError(data)

    async def analyze_transcript(
        self,
        transcript: str,
        preset: str,
        humor_style: str,
        model: Optional[str] = None,
        custom_prompt: str = "",
    ) -> dict[str, Any]:
        selected_model = (model or self.config.analysis_model).strip() or self.config.analysis_model
        self.analyzer.model = selected_model

        async with self._lock:
            result = await self.analyzer.run_preset(
                transcript=transcript,
                preset_name=preset,
                humor_style=humor_style,
                custom_prompt=custom_prompt,
            )
        return result.to_dict()


def _configure_logging() -> None:
    if LOGGER.handlers:
        return

    log_path = ProjectPaths.LOGS_DIR / "private_web.log"
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        "%Y-%m-%dT%H:%M:%S%z",
    )

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=1_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(formatter)

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)

    LOGGER.setLevel(logging.INFO)
    LOGGER.addHandler(file_handler)
    LOGGER.addHandler(stream_handler)
    LOGGER.propagate = False


def _extract_client_ip(request: Request, config: ServiceConfig) -> str:
    direct_ip = request.client.host if request.client else ""
    if not config.trust_proxy_headers:
        return direct_ip

    forwarded_for = request.headers.get("x-forwarded-for", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()

    return direct_ip


def _ip_allowed(client_ip: str, config: ServiceConfig) -> bool:
    if not client_ip:
        return False

    try:
        parsed_ip = ipaddress.ip_address(client_ip)
    except ValueError:
        return False

    if config.allowed_ips:
        return client_ip in config.allowed_ips

    if config.allow_tailscale_ips:
        return parsed_ip in TAILSCALE_NETWORK

    return False


def _token_allowed(request: Request, config: ServiceConfig) -> bool:
    if not config.server_key:
        return False

    candidate_values = [
        request.headers.get("x-subtext-key", ""),
        request.cookies.get("subtext_key", ""),
    ]
    return any(secrets.compare_digest(value, config.server_key) for value in candidate_values if value)


@asynccontextmanager
async def lifespan(app: FastAPI):
    _configure_logging()
    config = ServiceConfig()
    service = PrivateTranscriptionService(config)
    app.state.config = config
    app.state.service = service

    await service.startup()
    LOGGER.info(
        "service_started model=%s backend=%s tailscale_ip_filter=%s explicit_ips=%s",
        config.model_name,
        service.transcriber.backend,
        config.allow_tailscale_ips,
        sorted(config.allowed_ips),
    )
    try:
        yield
    finally:
        await service.shutdown()


app = FastAPI(
    title="Subtext Private Service",
    description="Warm-model Whisper transcription service for Tailscale use.",
    lifespan=lifespan,
)

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    started_at = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        duration_ms = (time.perf_counter() - started_at) * 1000
        client_ip = request.client.host if request.client else "-"
        LOGGER.exception(
            "request_failed method=%s path=%s client=%s duration_ms=%.1f",
            request.method,
            request.url.path,
            client_ip,
            duration_ms,
        )
        raise

    duration_ms = (time.perf_counter() - started_at) * 1000
    client_ip = request.client.host if request.client else "-"
    LOGGER.info(
        "request method=%s path=%s status=%s client=%s duration_ms=%.1f",
        request.method,
        request.url.path,
        response.status_code,
        client_ip,
        duration_ms,
    )
    return response


@app.middleware("http")
async def api_security_middleware(request: Request, call_next):
    if request.url.path in {"/health"} or request.url.path.startswith("/static"):
        return await call_next(request)
    if request.url.path == "/":
        return await call_next(request)

    config: ServiceConfig = request.app.state.config
    client_ip = _extract_client_ip(request, config)
    if _token_allowed(request, config) or _ip_allowed(client_ip, config):
        return await call_next(request)

    if not config.server_key and not config.allow_tailscale_ips and not config.allowed_ips:
        return JSONResponse(
            status_code=503,
            content={"detail": (
                "Access control is not configured. Set SUBTEXT_SERVER_KEY or "
                "SUBTEXT_ALLOWED_IPS before exposing this service through Tailscale."
            )},
        )

    return JSONResponse(status_code=403, content={"detail": "Forbidden."})


@app.get("/", response_class=HTMLResponse)
async def index() -> HTMLResponse:
    index_html = STATIC_DIR / "index.html"
    if not index_html.exists():
        raise HTTPException(status_code=404, detail="Static files not found.")
    return HTMLResponse(index_html.read_text(encoding="utf-8"))


@app.get("/health")
async def health(request: Request) -> dict[str, str]:
    service: PrivateTranscriptionService = request.app.state.service
    return {
        "status": "ok",
        "model": service.transcriber.model_name,
        "backend": service.transcriber.backend,
        "device": service.transcriber.device,
        "analysis_model": service.config.analysis_model,
    }


@app.get("/analysis/meta", response_model=AnalysisMetaResponse)
async def analysis_meta(request: Request) -> AnalysisMetaResponse:
    service: PrivateTranscriptionService = request.app.state.service
    available_models = await service.list_analysis_models()

    preferred_models: List[str] = []
    seen: set[str] = set()
    for name in service.config.preferred_analysis_models + available_models:
        normalized = name.strip()
        if normalized and normalized not in seen:
            preferred_models.append(normalized)
            seen.add(normalized)

    return AnalysisMetaResponse(
        default_model=service.config.analysis_model,
        preferred_models=preferred_models,
        available_models=available_models,
        presets=OllamaAnalyzer.get_presets(),
        humor_styles=OllamaAnalyzer.get_humor_styles(),
    )


@app.post("/analyze")
async def analyze(
    request: Request,
    payload: AnalyzeRequest,
) -> dict[str, Any]:
    service: PrivateTranscriptionService = request.app.state.service

    try:
        result = await service.analyze_transcript(
            transcript=payload.transcript,
            preset=payload.preset,
            humor_style=payload.humor_style,
            model=payload.model,
            custom_prompt=payload.custom_prompt,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error

    LOGGER.info(
        "analyzed_transcript preset=%s style=%s model=%s chars=%s items=%s",
        payload.preset,
        payload.humor_style,
        result["model"],
        len(payload.transcript),
        len(result.get("items", [])),
    )
    return result


@app.post("/download-video")
async def download_video(
    request: Request,
    url: str = Form(default=""),
) -> FileResponse:
    cleaned_url = url.strip()
    if not cleaned_url:
        raise HTTPException(status_code=400, detail="URL is required.")

    service: PrivateTranscriptionService = request.app.state.service
    async with service._lock:
        downloaded_path = await service.downloader.download_best_video(cleaned_url)
    media_type, _ = mimetypes.guess_type(downloaded_path.name)
    LOGGER.info("download_only filename=%s size=%s", downloaded_path.name, downloaded_path.stat().st_size)

    return FileResponse(
        path=downloaded_path,
        media_type=media_type or "application/octet-stream",
        filename=downloaded_path.name,
        background=BackgroundTask(lambda: downloaded_path.unlink(missing_ok=True)),
    )


@app.post("/transcribe")
async def transcribe(
    request: Request,
    url: str = Form(default=""),
    file: Optional[UploadFile] = File(default=None),
) -> dict[str, float | str]:
    service: PrivateTranscriptionService = request.app.state.service

    has_url = bool(url.strip())
    has_file = file is not None and bool(file.filename)
    if has_url == has_file:
        raise HTTPException(
            status_code=400,
            detail="Provide either a Web URL or one uploaded audio/video file.",
        )

    if has_url:
        result = await service.transcribe_url(url)
        LOGGER.info(
            "transcribed_url duration=%.3f latency=%.3f chars=%s",
            result["duration"],
            result["latency"],
            len(str(result["text"])),
        )
        return result

    assert file is not None
    result = await service.transcribe_upload(file)
    LOGGER.info(
        "transcribed_file filename=%s duration=%.3f latency=%.3f chars=%s",
        file.filename,
        result["duration"],
        result["latency"],
        len(str(result["text"])),
    )
    return result


@app.post("/api/transcribe")
async def api_transcribe(request: Request, file: UploadFile = File(...)) -> dict[str, float | str]:
    return await transcribe(request, file=file)


@app.post("/transcribe/stream")
async def transcribe_stream(request: Request, url: str = Form(default=""), file: Optional[UploadFile] = File(default=None)):
    """
    Stream transcription chunks as Server-Sent Events.
    Yields 'chunk' events with text fragments as they are transcribed.
    """
    service: PrivateTranscriptionService = request.app.state.service

    has_url = bool(url.strip())
    has_file = file is not None and bool(file.filename)
    if has_url == has_file:
        raise HTTPException(
            status_code=400,
            detail="Provide either a Web URL or one uploaded audio/video file.",
        )

    async def event_stream():
        started_at = time.perf_counter()
        loop = asyncio.get_running_loop()
        progress_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        def progress_callback(progress) -> None:
            loop.call_soon_threadsafe(
                progress_queue.put_nowait,
                {
                    "stage": progress.stage,
                    "percent": round(progress.percent, 1),
                    "message": progress.message,
                },
            )

        async def flush_progress_events() -> list[dict[str, Any]]:
            events: list[dict[str, Any]] = []
            while not progress_queue.empty():
                events.append(await progress_queue.get())
            return events

        try:
            if has_url:
                downloaded_path: Optional[Path] = None
                try:
                    async with service._lock:
                        downloaded_path = await service.downloader.download(url.strip())
                        duration = service.transcriber.get_audio_duration(downloaded_path)

                        async for text_chunk in service.transcriber.transcribe_stream(
                            downloaded_path,
                            progress_callback=progress_callback,
                        ):
                            for progress_event in await flush_progress_events():
                                yield _sse_event("progress", progress_event)
                            if text_chunk:
                                yield _sse_event("chunk", {"text": text_chunk})

                    for progress_event in await flush_progress_events():
                        yield _sse_event("progress", progress_event)
                    latency = time.perf_counter() - started_at
                    yield _sse_event(
                        "done",
                        {"duration": round(duration, 3), "latency": round(latency, 3)},
                    )
                finally:
                    if downloaded_path:
                        try:
                            downloaded_path.unlink(missing_ok=True)
                        except Exception:
                            LOGGER.warning("cleanup_failed path=%s", downloaded_path)

            else:
                assert file is not None
                suffix = Path(file.filename or "upload.wav").suffix.lower()
                if suffix not in ALLOWED_EXTENSIONS:
                    raise HTTPException(
                        status_code=400,
                        detail="Unsupported file type.",
                    )

                temp_path = ProjectPaths.RUNTIME_DIR / f"upload_{uuid.uuid4().hex}{suffix}"
                try:
                    with temp_path.open("wb") as handle:
                        while True:
                            chunk_bytes = await file.read(1024 * 1024)
                            if not chunk_bytes:
                                break
                            handle.write(chunk_bytes)

                    async with service._lock:
                        duration = service.transcriber.get_audio_duration(temp_path)

                        async for text_chunk in service.transcriber.transcribe_stream(
                            temp_path,
                            progress_callback=progress_callback,
                        ):
                            for progress_event in await flush_progress_events():
                                yield _sse_event("progress", progress_event)
                            if text_chunk:
                                yield _sse_event("chunk", {"text": text_chunk})

                    for progress_event in await flush_progress_events():
                        yield _sse_event("progress", progress_event)
                    latency = time.perf_counter() - started_at
                    yield _sse_event(
                        "done",
                        {"duration": round(duration, 3), "latency": round(latency, 3)},
                    )

                finally:
                    await file.close()
                    try:
                        temp_path.unlink(missing_ok=True)
                    except Exception:
                        LOGGER.warning("cleanup_failed path=%s", temp_path)

        except HTTPException as error:
            yield _sse_event("error", {"detail": error.detail})
        except Exception as e:
            yield _sse_event("error", {"detail": str(e)})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ── Chat endpoints ────────────────────────────────────────────────────────────

@app.get("/chat/models")
async def chat_models(request: Request) -> dict[str, Any]:
    """Return locally available Ollama models for the chat selector."""
    service: PrivateTranscriptionService = request.app.state.service
    models = await service.list_analysis_models()
    preferred = list(service.config.preferred_analysis_models)
    # Merge: preferred first, then any extra discovered models
    seen: set[str] = set(preferred)
    for m in models:
        if m not in seen:
            preferred.append(m)
            seen.add(m)
    return {
        "models": preferred,
        "default": service.config.analysis_model,
        "copenet_configured": bool(service.config.copenet_api_url),
    }


@app.post("/chat/stream")
async def chat_stream(request: Request, payload: ChatRequest) -> StreamingResponse:
    """
    Stream a chat response as SSE tokens.

    SSE events emitted:
      event: token   data: {"text": "<fragment>"}
      event: done    data: {}
      event: error   data: {"detail": "<message>"}

    CopeNet hook-up
    ───────────────
    When COPENET_API_URL is set the service config will have
    ``copenet_api_url`` populated. Wire up the proxy here by replacing
    the ``service.stream_chat(...)`` call below with a CopeNet HTTP
    request — the yield contract (raw token strings) stays identical.
    """
    service: PrivateTranscriptionService = request.app.state.service
    config: ServiceConfig = request.app.state.config

    model = (payload.model or config.analysis_model).strip() or config.analysis_model

    # Build message list
    messages: list[dict] = []

    if payload.transcript_context and payload.transcript_context.strip():
        messages.append({
            "role": "system",
            "content": (
                "You have access to the following transcript. When the user's "
                "question relates to this content, ground your answer in it. "
                "If something isn't covered, say so.\n\n"
                f"Transcript:\n{payload.transcript_context[:12_000]}"
            ),
        })

    for msg in payload.history:
        messages.append({"role": msg.role, "content": msg.content})

    messages.append({"role": "user", "content": payload.message})

    # ── CopeNet proxy stub ────────────────────────────────────────────────────
    # TODO: when CopeNet is ready, check config.copenet_api_url here and
    # replace the stream_chat call with an HTTP SSE proxy to CopeNet.
    # Example shape (adjust to CopeNet's actual contract):
    #
    #   if config.copenet_api_url:
    #       return _proxy_copenet(config.copenet_api_url, messages, model)
    # ─────────────────────────────────────────────────────────────────────────

    async def event_gen():
        try:
            async for token in service.stream_chat(messages, model):
                yield _sse_event("token", {"text": token})
            yield _sse_event("done", {})
        except RuntimeError as exc:
            yield _sse_event("error", {"detail": str(exc)})
        except Exception as exc:  # noqa: BLE001
            yield _sse_event("error", {"detail": str(exc)})

    LOGGER.info(
        "chat_stream model=%s history_len=%s has_context=%s",
        model,
        len(payload.history),
        bool(payload.transcript_context),
    )

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
