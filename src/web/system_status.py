"""
System status helpers: memory snapshot + per-backend model inventory.

Used by the Models panel in the private web service so the user can see what
the Mac mini is doing and decide what to load or unload before chatting.
Pure helpers — no FastAPI dependency. All blocking calls are wrapped in
``asyncio.to_thread`` so they don't stall the event loop.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Optional

import psutil

LOGGER = logging.getLogger("subtext.private_service.system_status")

# RAM cost ≈ on-disk weight × this factor. Covers KV cache + activation
# overhead for a typical chat session. Pretty rough but good enough for the
# load-safety warning we use it for.
RAM_OVERHEAD_MULT = 1.15


def memory_snapshot() -> dict[str, Any]:
    vm = psutil.virtual_memory()
    sm = psutil.swap_memory()
    free_pct = vm.available / vm.total if vm.total else 0
    swap_pct = sm.used / sm.total if sm.total else 0
    if free_pct < 0.10 or swap_pct > 0.60:
        pressure = "high"
    elif free_pct < 0.25 or swap_pct > 0.30:
        pressure = "moderate"
    else:
        pressure = "low"
    return {
        "total_bytes": vm.total,
        "used_bytes": vm.used,
        "available_bytes": vm.available,
        "percent_used": vm.percent,
        "swap_total_bytes": sm.total,
        "swap_used_bytes": sm.used,
        "pressure": pressure,
    }


def estimate_ram_for_disk(disk_bytes: int) -> int:
    if disk_bytes <= 0:
        return 0
    return int(disk_bytes * RAM_OVERHEAD_MULT)


async def ollama_model_inventory(client) -> dict[str, Any]:
    """Installed + loaded Ollama models with sizes. Returns {} on any failure."""
    def _gather() -> dict[str, Any]:
        listed = client.list()
        ps = client.ps()
        loaded_names = {getattr(m, "model", None) for m in getattr(ps, "models", [])}
        installed = []
        for m in getattr(listed, "models", []):
            name = getattr(m, "model", None) or getattr(m, "name", None)
            if not name:
                continue
            size = int(getattr(m, "size", 0) or 0)
            installed.append({
                "name": name,
                "size_bytes": size,
                "ram_estimate_bytes": estimate_ram_for_disk(size),
                "loaded": name in loaded_names,
            })
        return {"installed": installed}

    try:
        return await asyncio.to_thread(_gather)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("ollama_inventory_failed err=%s", exc)
        return {"installed": [], "error": str(exc)}


async def lmstudio_model_inventory(provider) -> dict[str, Any]:
    """Installed + loaded LM Studio models. Sizes when available."""
    if provider is None:
        return {"installed": [], "reachable": False}

    import lmstudio as lms

    def _gather() -> dict[str, Any]:
        downloaded = lms.list_downloaded_models("llm")
        loaded = lms.list_loaded_models("llm")
        loaded_keys: set[str] = set()
        for m in loaded:
            key = getattr(m, "model_key", None) or getattr(m, "identifier", None)
            if key:
                loaded_keys.add(key)
        installed = []
        for m in downloaded:
            name = getattr(m, "model_key", None) or getattr(m, "identifier", None)
            if not name:
                continue
            size = int(getattr(m, "size_bytes", 0) or 0)
            installed.append({
                "name": name,
                "size_bytes": size,
                "ram_estimate_bytes": estimate_ram_for_disk(size),
                "loaded": name in loaded_keys,
            })
        return {"installed": installed, "reachable": True}

    try:
        return await asyncio.to_thread(_gather)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("lmstudio_inventory_failed err=%s", exc)
        return {"installed": [], "reachable": False, "error": str(exc)}


def whisper_status(transcriber) -> dict[str, Any]:
    if transcriber is None:
        return {"loaded": False}
    loaded = getattr(transcriber, "model", None) is not None
    return {
        "name": getattr(transcriber, "model_name", ""),
        "backend": getattr(transcriber, "backend", ""),
        "device": getattr(transcriber, "device", ""),
        "loaded": loaded,
    }


async def load_ollama_model(client, name: str, keep_alive: str = "10m") -> None:
    """Warm a model into memory via a no-op generate request."""
    def _warm() -> None:
        client.generate(model=name, prompt="", keep_alive=keep_alive)

    await asyncio.to_thread(_warm)


async def unload_ollama_model(client, name: str) -> None:
    """Evict a model from memory via keep_alive=0 no-op."""
    def _evict() -> None:
        client.generate(model=name, prompt="", keep_alive=0)

    await asyncio.to_thread(_evict)


async def load_lmstudio_model(name: str) -> None:
    import lmstudio as lms

    def _warm() -> None:
        # Touching .llm() with a key triggers auto-load.
        lms.llm(name)

    await asyncio.to_thread(_warm)


async def unload_lmstudio_model(name: Optional[str]) -> None:
    """Unload one model by identifier, or all loaded LLMs if name is None."""
    import lmstudio as lms

    def _evict() -> None:
        if name:
            try:
                lms.get_default_client().llm.unload(name)
            except Exception:  # noqa: BLE001
                pass
            return
        for m in lms.list_loaded_models("llm"):
            identifier = getattr(m, "identifier", None) or getattr(m, "model_key", None)
            if identifier:
                try:
                    lms.get_default_client().llm.unload(identifier)
                except Exception:  # noqa: BLE001
                    pass

    await asyncio.to_thread(_evict)
