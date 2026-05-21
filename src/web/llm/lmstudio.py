"""
LM Studio chat provider.

Mirrors the contract that PrivateTranscriptionService already exposes for
Ollama-backed chat: an async iterator of raw token strings for streaming
and an async list of model identifiers for the selector. Adds explicit
load/unload entry points so the service can free VRAM when idle.

Uses the synchronous `lmstudio` SDK from a worker thread to match the
existing Ollama integration pattern in src/web/server.py.
"""
from __future__ import annotations

import asyncio
import io
import logging
from typing import Any, AsyncGenerator, List, Optional, Sequence

import lmstudio as lms

LOGGER = logging.getLogger("subtext.private_service.lmstudio")


def _model_key(obj: Any) -> Optional[str]:
    return getattr(obj, "model_key", None) or getattr(obj, "identifier", None)


class LMStudioProvider:
    """Thin async wrapper around the synchronous lmstudio SDK.

    LM Studio's SDK is process-singleton-friendly (`lms.llm(...)` reuses a
    default client). We rely on that rather than holding our own Client
    handle so reconnects after LM Studio restarts are transparent.
    """

    def __init__(self, host: Optional[str] = None) -> None:
        self._host = (host or "").strip() or None

    async def _run(self, fn, *args, **kwargs):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: fn(*args, **kwargs))

    async def list_models(self) -> List[str]:
        def _list() -> List[str]:
            downloaded = lms.list_downloaded_models("llm")
            keys: List[str] = []
            for m in downloaded:
                key = _model_key(m)
                if key:
                    keys.append(key)
            return keys

        try:
            return await self._run(_list)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("lmstudio_list_failed err=%s", exc)
            return []

    async def list_loaded(self) -> List[str]:
        def _list() -> List[str]:
            loaded = lms.list_loaded_models("llm")
            keys: List[str] = []
            for m in loaded:
                key = _model_key(m)
                if key:
                    keys.append(key)
            return keys

        try:
            return await self._run(_list)
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("lmstudio_list_loaded_failed err=%s", exc)
            return []

    async def unload_all(self) -> None:
        def _unload() -> None:
            for m in lms.list_loaded_models("llm"):
                identifier = getattr(m, "identifier", None) or _model_key(m)
                if not identifier:
                    continue
                try:
                    lms.get_default_client().llm.unload(identifier)
                    LOGGER.info("lmstudio_unloaded model=%s", identifier)
                except Exception as exc:  # noqa: BLE001
                    LOGGER.warning("lmstudio_unload_failed model=%s err=%s", identifier, exc)

        await self._run(_unload)

    async def stream_chat(
        self,
        messages: List[dict],
        model: str,
        images: Optional[Sequence[bytes]] = None,
    ) -> AsyncGenerator[str, None]:
        """Yield raw token strings from an LM Studio chat completion.

        Mirrors PrivateTranscriptionService.stream_chat: yields strings,
        raises RuntimeError on failure. LM Studio auto-loads the model on
        first use of `lms.llm(model)`.

        When ``images`` is provided, the bytes are attached to the final
        user turn via ``Chat.add_user_message(..., images=[...])``. This
        requires the loaded LM Studio model to be multimodal; non-vision
        models will return a clear error from the SDK.
        """
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()

        image_bytes_list = list(images or [])

        def _blocking_stream() -> None:
            try:
                llm = lms.llm(model)

                if image_bytes_list:
                    # Vision path — rebuild chat manually so we can attach
                    # images to the final user message.
                    chat = lms.Chat()
                    history = messages[:-1] if messages else []
                    for msg in history:
                        role = msg.get("role")
                        content = msg.get("content", "")
                        if role == "system":
                            chat.add_system_prompt(content)
                        elif role == "assistant":
                            chat.add_assistant_response(content)
                        else:
                            chat.add_user_message(content)
                    last = messages[-1] if messages else {"role": "user", "content": ""}
                    handles = [
                        lms.prepare_image(io.BytesIO(b)) for b in image_bytes_list
                    ]
                    chat.add_user_message(last.get("content", ""), images=handles)
                else:
                    chat = lms.Chat.from_history({"messages": messages})

                for fragment in llm.respond_stream(chat):
                    content = getattr(fragment, "content", None)
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
