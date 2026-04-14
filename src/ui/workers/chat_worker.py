"""
Streaming chat worker for local Ollama LLM conversations.
"""
from __future__ import annotations

from PySide6.QtCore import QThread, Signal

import ollama


class ChatWorker(QThread):
    """QThread that streams tokens from an Ollama chat call."""

    token_received = Signal(str)       # each streamed token
    response_complete = Signal(str)    # full assembled response when done
    error_occurred = Signal(str)

    def __init__(self, messages: list[dict], model: str):
        super().__init__()
        self.messages = messages
        self.model = model
        self._full_response = ""

    def run(self):
        try:
            client = ollama.Client()
            stream = client.chat(
                model=self.model,
                messages=self.messages,
                stream=True,
            )
            self._full_response = ""
            for chunk in stream:
                if self.isInterruptionRequested():
                    break
                content = self._extract_content(chunk)
                if content:
                    self._full_response += content
                    self.token_received.emit(content)
            self.response_complete.emit(self._full_response)
        except Exception as exc:
            self.error_occurred.emit(str(exc))

    @staticmethod
    def _extract_content(chunk) -> str:
        if isinstance(chunk, dict):
            return chunk.get("message", {}).get("content", "") or ""
        msg = getattr(chunk, "message", None)
        if msg is not None:
            return str(getattr(msg, "content", "") or "")
        return ""
