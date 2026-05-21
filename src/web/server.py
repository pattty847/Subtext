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
from src.web.chat_store import ChatStore, transcript_hash as _transcript_hash
from src.web.llm.lmstudio import LMStudioProvider
from src.web import system_status

ProjectPaths.initialize()

# Register PWA manifest MIME type so /static/manifest.webmanifest serves with
# the right content-type when iOS Safari probes it for Add-to-Home-Screen.
mimetypes.add_type("application/manifest+json", ".webmanifest")

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
        # ── Chat provider ─────────────────────────────────────────────────────
        # SUBTEXT_CHAT_PROVIDER=ollama (default) or lmstudio.
        # When set to lmstudio, /chat/models and /chat/stream are routed to
        # the local LM Studio server (typically http://localhost:1234). The
        # idle watchdog will then auto-unload after SUBTEXT_CHAT_IDLE_SECONDS.
        provider = os.getenv("SUBTEXT_CHAT_PROVIDER", "ollama").strip().lower()
        self.chat_provider = provider if provider in {"ollama", "lmstudio"} else "ollama"
        self.lmstudio_host = os.getenv("LMSTUDIO_HOST", "").strip() or None
        try:
            self.chat_idle_seconds = max(60, int(os.getenv("SUBTEXT_CHAT_IDLE_SECONDS", "600")))
        except ValueError:
            self.chat_idle_seconds = 600
        try:
            self.transcribe_idle_seconds = max(60, int(os.getenv("SUBTEXT_TRANSCRIBE_IDLE_SECONDS", "600")))
        except ValueError:
            self.transcribe_idle_seconds = 600
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
    # When set, the server appends the user prompt + final assistant reply to
    # this thread after streaming completes.
    thread_id: Optional[str] = Field(default=None)
    # Optional list of data URLs (data:image/...;base64,...) attached to this
    # turn. Routed only to multimodal-capable providers (LM Studio for now).
    images: List[str] = Field(default_factory=list)


# Soft cap on attached image bytes after base64 decode. Anything beyond this
# is rejected at the route boundary so a 50 MB screenshot can't OOM the box.
MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGES_PER_TURN = 4


def _decode_data_url(url: str) -> bytes:
    """data:image/png;base64,XXX → raw bytes. Raises ValueError on garbage."""
    import base64
    s = (url or "").strip()
    if not s.startswith("data:"):
        raise ValueError("image is not a data URL")
    _, _, payload = s.partition(",")
    if not payload:
        raise ValueError("image data URL has no payload")
    try:
        return base64.b64decode(payload, validate=False)
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"could not decode image: {exc}") from exc


class ThreadCreateRequest(BaseModel):
    transcript_context: Optional[str] = Field(default=None)
    title: str = Field(default="")
    model: str = Field(default="")


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
        # Both providers always exist; reachability is detected per-request.
        # config.chat_provider is just the default to bias the selector toward.
        self.lmstudio: LMStudioProvider = LMStudioProvider(host=config.lmstudio_host)
        self._last_chat_activity: Optional[float] = None
        self._last_transcribe_activity: Optional[float] = None
        self.chat_store = ChatStore(ProjectPaths.RUNTIME_DIR / "subtext_chat.db")

    async def startup(self) -> None:
        # Whisper is lazy-loaded on first transcribe and unloaded after
        # ``transcribe_idle_seconds`` of inactivity. ~600MB-1GB reclaimed
        # when idle, ~1s cold-start tax on the first transcribe of a window.
        LOGGER.info(
            "whisper_lazy model=%s backend=%s device=%s compute_type=%s idle_seconds=%s",
            self.transcriber.model_name,
            self.transcriber.backend,
            self.transcriber.device,
            self.transcriber.compute_type,
            self.config.transcribe_idle_seconds,
        )

    async def shutdown(self) -> None:
        if self.transcriber.model is not None:
            self.transcriber.unload_model()
            LOGGER.info("whisper_unloaded")

    def _touch_transcribe(self) -> None:
        self._last_transcribe_activity = time.time()

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
                self._touch_transcribe()
                duration = self.transcriber.get_audio_duration(temp_path)
                text = await self.transcriber.transcribe(temp_path)

            latency = time.perf_counter() - started_at
            return {
                "text": text,
                "duration": round(duration, 3),
                "latency": round(latency, 3),
            }
        finally:
            self._touch_transcribe()
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
                self._touch_transcribe()
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
            self._touch_transcribe()
            if downloaded_path is not None:
                try:
                    downloaded_path.unlink(missing_ok=True)
                except Exception:
                    LOGGER.warning("cleanup_failed path=%s", downloaded_path)

    async def list_analysis_models(self) -> List[str]:
        """Bare list of Ollama-side model names used by the legacy /analyze path."""
        return await self.analyzer.list_available_models()

    async def aggregate_chat_models(self) -> dict[str, Any]:
        """Aggregate installed + loaded models across every chat provider.

        Returns
        ───────
        ``{"models": [{"id", "provider", "name", "loaded"}], "providers": {...}, "default"}``

        Each ``id`` is ``provider:name``. The frontend uses that as the
        selector's value; the server parses it back in :meth:`stream_chat`.
        ``providers`` tells the UI which backends were reachable so it can
        say "lmstudio is offline" instead of just showing nothing.
        """
        ollama_models, lmstudio_models = await asyncio.gather(
            self.analyzer.list_available_models(),
            self.lmstudio.list_models(),
        )

        # Loaded sets per provider (best-effort; failures degrade to empty).
        ollama_loaded: set[str] = set()
        try:
            ps = await asyncio.to_thread(self.analyzer.client.ps)
            for m in getattr(ps, "models", []):
                name = getattr(m, "model", None) or getattr(m, "name", None)
                if name:
                    ollama_loaded.add(name)
        except Exception:  # noqa: BLE001
            pass

        lmstudio_loaded_list = await self.lmstudio.list_loaded()
        lmstudio_loaded = set(lmstudio_loaded_list)
        lmstudio_reachable = bool(lmstudio_models) or bool(lmstudio_loaded_list)

        models: list[dict[str, Any]] = []
        for name in ollama_models:
            models.append({
                "id": f"ollama:{name}",
                "provider": "ollama",
                "name": name,
                "loaded": name in ollama_loaded,
            })
        for name in lmstudio_models:
            models.append({
                "id": f"lmstudio:{name}",
                "provider": "lmstudio",
                "name": name,
                "loaded": name in lmstudio_loaded,
            })

        # Sort by provider, then alphabetical model name (case-insensitive).
        models.sort(key=lambda m: (m["provider"], m["name"].lower()))

        # Default selection: a loaded model on the preferred provider if any,
        # otherwise first loaded anywhere, otherwise first in the list.
        preferred = self.config.chat_provider
        default = ""
        loaded_pref = [m for m in models if m["loaded"] and m["provider"] == preferred]
        loaded_any  = [m for m in models if m["loaded"]]
        if loaded_pref:
            default = loaded_pref[0]["id"]
        elif loaded_any:
            default = loaded_any[0]["id"]
        elif models:
            # Fall back to first model on the preferred provider, else first overall.
            preferred_first = next((m for m in models if m["provider"] == preferred), None)
            default = (preferred_first or models[0])["id"]

        return {
            "models": models,
            "default": default,
            "providers": {
                "ollama":   {"reachable": True},
                "lmstudio": {"reachable": lmstudio_reachable},
            },
            "preferred_provider": preferred,
        }

    def parse_model_id(self, model_id: str) -> tuple[str, str]:
        """Split ``provider:model`` into ``(provider, model_name)``.

        If no prefix is present, falls back to the configured default
        provider. ``provider`` is normalized to lowercase.
        """
        raw = (model_id or "").strip()
        if ":" in raw:
            prov, _, name = raw.partition(":")
            prov = prov.strip().lower()
            if prov in {"ollama", "lmstudio"}:
                return prov, name.strip()
        return self.config.chat_provider, raw

    async def stream_chat(
        self,
        messages: List[dict],
        model_id: str,
        images: Optional[List[bytes]] = None,
    ) -> AsyncGenerator[str, None]:
        """Stream chat tokens from whichever provider ``model_id`` names.

        Yields raw token strings; raises RuntimeError on model failure.
        Updates ``_last_chat_activity`` on entry AND exit so the idle
        watchdog can't unload a model that's actively responding. When
        ``images`` is set, only the LM Studio provider can consume it
        (Ollama vision is unwired for now and would silently drop them).
        """
        provider, model_name = self.parse_model_id(model_id)
        self._last_chat_activity = time.time()

        if images and provider != "lmstudio":
            raise RuntimeError(
                "Image attachments only work with LM Studio multimodal models. "
                "Pick an LM Studio model and make sure it supports vision."
            )

        if provider == "lmstudio":
            try:
                async for token in self.lmstudio.stream_chat(messages, model_name, images=images):
                    yield token
            finally:
                self._last_chat_activity = time.time()
            return

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        def _blocking_stream() -> None:
            try:
                for chunk in self.analyzer.client.chat(
                    model=model_name,
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

        try:
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
        finally:
            self._last_chat_activity = time.time()

    async def maybe_unload_idle_transcriber(self) -> None:
        """Free Whisper from RAM when nothing's been transcribed in a while.

        Safe to call from a watchdog loop: bails out early if no activity has
        ever been recorded, if the model isn't actually loaded, or if a
        transcribe is still in flight (lock acquisition serializes with the
        live request path so we never yank the model out from under one).
        """
        if self._last_transcribe_activity is None:
            return
        if self.transcriber.model is None:
            self._last_transcribe_activity = None
            return
        idle = time.time() - self._last_transcribe_activity
        if idle < self.config.transcribe_idle_seconds:
            return
        async with self._lock:
            # Re-check after acquiring; a transcribe could have completed
            # while we were waiting.
            if self.transcriber.model is None:
                return
            idle = time.time() - self._last_transcribe_activity
            if idle < self.config.transcribe_idle_seconds:
                return
            LOGGER.info("whisper_idle_unload idle_seconds=%.0f", idle)
            await asyncio.to_thread(self.transcriber.unload_model)
        self._last_transcribe_activity = None

    async def maybe_unload_idle_chat(self) -> None:
        """Unload LM Studio models if no chat activity within the idle window.

        Ollama models self-evict via their own ``keep_alive`` so we only need
        to actively manage LM Studio here.
        """
        if self._last_chat_activity is None:
            return
        idle = time.time() - self._last_chat_activity
        if idle < self.config.chat_idle_seconds:
            return
        loaded = await self.lmstudio.list_loaded()
        if not loaded:
            self._last_chat_activity = None
            return
        LOGGER.info("lmstudio_idle_unload idle_seconds=%.0f models=%s", idle, loaded)
        await self.lmstudio.unload_all()
        self._last_chat_activity = None

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
    await service.chat_store.init_schema()
    LOGGER.info(
        "service_started model=%s backend=%s chat_provider=%s tailscale_ip_filter=%s explicit_ips=%s",
        config.model_name,
        service.transcriber.backend,
        config.chat_provider,
        config.allow_tailscale_ips,
        sorted(config.allowed_ips),
    )

    async def _idle_watchdog() -> None:
        while True:
            try:
                await asyncio.sleep(60)
                await service.maybe_unload_idle_chat()
                await service.maybe_unload_idle_transcriber()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                LOGGER.warning("idle_watchdog_iteration_failed err=%s", exc)

    watchdog_task = asyncio.create_task(_idle_watchdog(), name="subtext-idle-watchdog")
    LOGGER.info(
        "idle_watchdog_started chat=%s transcribe=%s",
        config.chat_idle_seconds,
        config.transcribe_idle_seconds,
    )

    try:
        yield
    finally:
        watchdog_task.cancel()
        try:
            await watchdog_task
        except asyncio.CancelledError:
            pass
        await service.lmstudio.unload_all()
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
    LOGGER.info("download_video filename=%s size=%s", downloaded_path.name, downloaded_path.stat().st_size)

    return FileResponse(
        path=downloaded_path,
        media_type=media_type or "application/octet-stream",
        filename=downloaded_path.name,
        background=BackgroundTask(lambda: downloaded_path.unlink(missing_ok=True)),
    )


@app.post("/download-audio")
async def download_audio(
    request: Request,
    url: str = Form(default=""),
) -> FileResponse:
    cleaned_url = url.strip()
    if not cleaned_url:
        raise HTTPException(status_code=400, detail="URL is required.")

    service: PrivateTranscriptionService = request.app.state.service
    async with service._lock:
        downloaded_path = await service.downloader.download_best_audio(cleaned_url)
    media_type, _ = mimetypes.guess_type(downloaded_path.name)
    LOGGER.info("download_audio filename=%s size=%s", downloaded_path.name, downloaded_path.stat().st_size)

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
        service._touch_transcribe()
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
        finally:
            service._touch_transcribe()

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
    """Return chat models from every backend, tagged with provider.

    Response shape::

        {
          "models": [
            {"id": "ollama:qwen3:8b", "provider": "ollama", "name": "qwen3:8b", "loaded": true},
            {"id": "lmstudio:llama-3.1-8b", "provider": "lmstudio", "name": "...", "loaded": false},
            …
          ],
          "default": "<provider>:<name>",
          "providers": {"ollama": {"reachable": true}, "lmstudio": {"reachable": false}},
          "preferred_provider": "ollama"
        }

    Sorted by provider then alphabetical model name. Empty when both
    backends are unreachable.
    """
    service: PrivateTranscriptionService = request.app.state.service
    payload = await service.aggregate_chat_models()
    payload["copenet_configured"] = bool(service.config.copenet_api_url)
    return payload


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

    # model is now a ``provider:name`` id from the multi-provider selector.
    # If the client omits a prefix, parse_model_id() falls back to the
    # default provider with this raw name.
    model = (payload.model or "").strip() or config.analysis_model

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

    # Validate + decode any attached images before kicking off the stream.
    image_bytes: list[bytes] = []
    if payload.images:
        if len(payload.images) > MAX_IMAGES_PER_TURN:
            raise HTTPException(
                status_code=413,
                detail=f"At most {MAX_IMAGES_PER_TURN} images per message.",
            )
        for url in payload.images:
            try:
                raw = _decode_data_url(url)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            if len(raw) > MAX_IMAGE_BYTES:
                raise HTTPException(
                    status_code=413,
                    detail=f"Image too large; max {MAX_IMAGE_BYTES // (1024 * 1024)} MB after decode.",
                )
            image_bytes.append(raw)

    # ── CopeNet proxy stub ────────────────────────────────────────────────────
    # TODO: when CopeNet is ready, check config.copenet_api_url here and
    # replace the stream_chat call with an HTTP SSE proxy to CopeNet.
    # Example shape (adjust to CopeNet's actual contract):
    #
    #   if config.copenet_api_url:
    #       return _proxy_copenet(config.copenet_api_url, messages, model)
    # ─────────────────────────────────────────────────────────────────────────

    async def event_gen():
        collected: list[str] = []
        had_error = False
        try:
            async for token in service.stream_chat(messages, model, images=image_bytes or None):
                collected.append(token)
                yield _sse_event("token", {"text": token})
            yield _sse_event("done", {})
        except RuntimeError as exc:
            had_error = True
            yield _sse_event("error", {"detail": str(exc)})
        except Exception as exc:  # noqa: BLE001
            had_error = True
            yield _sse_event("error", {"detail": str(exc)})
        finally:
            if not had_error and payload.thread_id and collected:
                reply_text = "".join(collected).strip()
                # Title backfill: first 60 chars of the user's first message.
                title_seed = payload.message.strip().splitlines()[0][:60]
                try:
                    await service.chat_store.append_messages(
                        payload.thread_id,
                        [
                            {"role": "user", "content": payload.message},
                            {"role": "assistant", "content": reply_text},
                        ],
                        model=model,
                        title_if_empty=title_seed,
                    )
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("chat_persist_failed thread=%s err=%s", payload.thread_id, exc)

    parsed_provider, parsed_name = service.parse_model_id(model)
    LOGGER.info(
        "chat_stream provider=%s model=%s history_len=%s has_context=%s images=%s thread=%s",
        parsed_provider,
        parsed_name,
        len(payload.history),
        bool(payload.transcript_context),
        len(image_bytes),
        payload.thread_id or "-",
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


# ── Chat thread endpoints ─────────────────────────────────────────────────────

@app.get("/chat/threads")
async def list_chat_threads(
    request: Request,
    transcript_hash: Optional[str] = None,
    transcript_context: Optional[str] = None,
) -> dict[str, Any]:
    """List chat threads.

    Pass ``transcript_hash`` to filter to a specific transcript's threads, or
    ``transcript_context`` to let the server compute the hash for you. With
    neither, returns the most-recent threads across everything.
    """
    service: PrivateTranscriptionService = request.app.state.service
    hash_value = transcript_hash
    if not hash_value and transcript_context:
        hash_value = _transcript_hash(transcript_context)
    threads = await service.chat_store.list_threads(hash_value)
    return {"threads": threads, "transcript_hash": hash_value}


@app.post("/chat/threads")
async def create_chat_thread(
    request: Request, payload: ThreadCreateRequest
) -> dict[str, Any]:
    service: PrivateTranscriptionService = request.app.state.service
    th = _transcript_hash(payload.transcript_context)
    text = payload.transcript_context.strip() if payload.transcript_context else None
    thread = await service.chat_store.create_thread(
        transcript_hash_value=th,
        transcript_text=text,
        title=payload.title.strip(),
        model=payload.model.strip(),
    )
    return thread


@app.get("/chat/threads/{thread_id}/messages")
async def get_chat_thread_messages(
    request: Request, thread_id: str
) -> dict[str, Any]:
    service: PrivateTranscriptionService = request.app.state.service
    thread = await service.chat_store.get_thread(thread_id)
    if thread is None:
        raise HTTPException(status_code=404, detail="Thread not found.")
    messages = await service.chat_store.get_messages(thread_id)
    return {"thread": thread, "messages": messages}


@app.delete("/chat/threads/{thread_id}")
async def delete_chat_thread(request: Request, thread_id: str) -> dict[str, bool]:
    service: PrivateTranscriptionService = request.app.state.service
    ok = await service.chat_store.delete_thread(thread_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Thread not found.")
    return {"deleted": True}


# ── System / model management endpoints ───────────────────────────────────────


class ModelActionRequest(BaseModel):
    backend: str = Field(min_length=1)   # "ollama" or "lmstudio"
    name: Optional[str] = Field(default=None)


@app.get("/system/status")
async def system_status_endpoint(request: Request) -> dict[str, Any]:
    """Memory snapshot + per-backend model inventory for the Models panel."""
    service: PrivateTranscriptionService = request.app.state.service
    memory = system_status.memory_snapshot()
    ollama = await system_status.ollama_model_inventory(service.analyzer.client)
    lmstudio = await system_status.lmstudio_model_inventory(service.lmstudio)
    whisper = system_status.whisper_status(service.transcriber)
    return {
        "memory": memory,
        "ollama": ollama,
        "lmstudio": lmstudio,
        "whisper": whisper,
        "chat_provider": service.config.chat_provider,
    }


@app.post("/system/load")
async def system_load(request: Request, payload: ModelActionRequest) -> dict[str, Any]:
    service: PrivateTranscriptionService = request.app.state.service
    backend = payload.backend.lower()
    name = (payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Model name required.")

    try:
        if backend == "ollama":
            await system_status.load_ollama_model(service.analyzer.client, name)
        elif backend == "lmstudio":
            await system_status.load_lmstudio_model(name)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown backend: {backend}")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("model_load_failed backend=%s name=%s err=%s", backend, name, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    LOGGER.info("model_loaded backend=%s name=%s", backend, name)
    return {"loaded": True, "backend": backend, "name": name}


@app.post("/system/unload")
async def system_unload(request: Request, payload: ModelActionRequest) -> dict[str, Any]:
    service: PrivateTranscriptionService = request.app.state.service
    backend = payload.backend.lower()
    name = (payload.name or "").strip() or None

    try:
        if backend == "ollama":
            if not name:
                raise HTTPException(status_code=400, detail="Model name required for ollama unload.")
            await system_status.unload_ollama_model(service.analyzer.client, name)
        elif backend == "lmstudio":
            await system_status.unload_lmstudio_model(name)
        else:
            raise HTTPException(status_code=400, detail=f"Unknown backend: {backend}")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("model_unload_failed backend=%s name=%s err=%s", backend, name, exc)
        raise HTTPException(status_code=500, detail=str(exc))

    LOGGER.info("model_unloaded backend=%s name=%s", backend, name or "<all>")
    return {"unloaded": True, "backend": backend, "name": name}
