"""
Local LLM chat interface with optional Subtext transcript context.

Two modes:
  - General chat: plain conversation with any local Ollama model.
  - Context chat: transcript injected as a system message so the model
    can answer questions grounded in the extracted content.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QFont, QKeyEvent, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.config.paths import ProjectPaths
from src.core.analyzer import OllamaAnalyzer
from src.ui.workers.chat_worker import ChatWorker

# ─── colour constants (kept local so the chat renderer is self-contained) ────
_C_USER_LABEL   = QColor("#14b8a6")
_C_AI_LABEL     = QColor("#6b7280")
_C_USER_TEXT    = QColor("#d1faf5")
_C_AI_TEXT      = QColor("#e8e8ea")
_C_ERROR        = QColor("#ef4444")
_C_DIVIDER      = QColor("#1e1e21")
_C_BG           = QColor("#0f0f11")
_C_MUTED        = QColor("#4b5563")

_TRANSCRIPT_SYSTEM_TEMPLATE = (
    "You are a helpful assistant with access to a transcript. "
    "When the user's question relates to the content, answer strictly from the "
    "transcript. If something isn't covered, say so clearly.\n\n"
    "Transcript:\n{transcript}"
)
_MAX_TRANSCRIPT_CHARS = 12_000


class _SendBox(QTextEdit):
    """QTextEdit that fires send_triggered on bare Enter; Shift+Enter → newline."""

    send_triggered: Signal = Signal()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        bare_enter = event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
        shifted = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
        if bare_enter and not shifted:
            self.send_triggered.emit()
        else:
            super().keyPressEvent(event)


class ChatTab(QWidget):
    """
    Full-featured local LLM chat tab.

    Pass ``get_transcript_fn`` (a zero-arg callable that returns the current
    transcript string) so the 'Use Active Transcript' button can inject it.
    """

    def __init__(self, get_transcript_fn: Optional[Callable[[], str]] = None):
        super().__init__()
        self._get_transcript = get_transcript_fn
        self.messages: list[dict] = []
        self._transcript_context: str = ""
        self._streaming: bool = False
        self._worker: Optional[ChatWorker] = None

        self._setup_ui()
        QTimer.singleShot(300, self._refresh_models)

    # ─── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_top_bar())
        root.addWidget(self._build_chat_display(), stretch=1)
        root.addWidget(self._build_input_area())

    def _build_top_bar(self) -> QFrame:
        bar = QFrame()
        bar.setObjectName("chatTopBar")
        bar.setFixedHeight(52)
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(16, 0, 16, 0)
        lay.setSpacing(10)

        # Model picker
        model_lbl = QLabel("Model")
        model_lbl.setProperty("class", "fieldLabel")

        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(210)
        self.model_combo.setToolTip("Local Ollama model to chat with")

        refresh_btn = QPushButton("Refresh")
        refresh_btn.setProperty("class", "secondary")
        refresh_btn.setFixedWidth(72)
        refresh_btn.setToolTip("Re-scan Ollama for available models")
        refresh_btn.clicked.connect(self._refresh_models)

        lay.addWidget(model_lbl)
        lay.addWidget(self.model_combo)
        lay.addWidget(refresh_btn)

        # Thin vertical rule
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.VLine)
        sep.setObjectName("topBarSep")
        lay.addWidget(sep)

        # Context controls
        self.context_status = QLabel("No context")
        self.context_status.setProperty("class", "muted")

        self._use_active_btn = QPushButton("Use Active Transcript")
        self._use_active_btn.setProperty("class", "secondary")
        self._use_active_btn.setToolTip(
            "Inject the transcript currently loaded in the Analyze tab"
        )
        self._use_active_btn.clicked.connect(self._load_active_transcript)

        self._browse_ctx_btn = QPushButton("Load File")
        self._browse_ctx_btn.setProperty("class", "secondary")
        self._browse_ctx_btn.setToolTip("Browse for a transcript .txt file")
        self._browse_ctx_btn.clicked.connect(self._browse_transcript)

        self._clear_ctx_btn = QPushButton("Clear")
        self._clear_ctx_btn.setProperty("class", "secondary")
        self._clear_ctx_btn.setToolTip("Remove transcript context")
        self._clear_ctx_btn.clicked.connect(self._clear_context)
        self._clear_ctx_btn.setVisible(False)

        lay.addWidget(self.context_status)
        lay.addWidget(self._use_active_btn)
        lay.addWidget(self._browse_ctx_btn)
        lay.addWidget(self._clear_ctx_btn)

        lay.addStretch()

        # Clear chat
        clear_chat_btn = QPushButton("Clear Chat")
        clear_chat_btn.setProperty("class", "secondary")
        clear_chat_btn.clicked.connect(self._clear_chat)
        lay.addWidget(clear_chat_btn)

        return bar

    def _build_chat_display(self) -> QWidget:
        wrapper = QWidget()
        wrapper.setObjectName("chatDisplayWrapper")
        lay = QVBoxLayout(wrapper)
        lay.setContentsMargins(0, 0, 0, 0)

        self._display = QTextEdit()
        self._display.setReadOnly(True)
        self._display.setObjectName("chatDisplay")
        self._display.setFrameStyle(QFrame.Shape.NoFrame)

        # Base document background
        self._display.setStyleSheet("QTextEdit#chatDisplay { background: #0f0f11; border: none; }")

        lay.addWidget(self._display)
        self._show_welcome()
        return wrapper

    def _build_input_area(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("chatInputArea")

        lay = QVBoxLayout(frame)
        lay.setContentsMargins(14, 10, 14, 14)
        lay.setSpacing(8)

        # Context badge (shown when transcript is active)
        self._ctx_badge = QLabel()
        self._ctx_badge.setObjectName("ctxBadge")
        self._ctx_badge.setVisible(False)
        lay.addWidget(self._ctx_badge)

        row = QHBoxLayout()
        row.setSpacing(8)

        self._input = _SendBox()
        self._input.setObjectName("chatTextInput")
        self._input.setPlaceholderText(
            "Message…   (Enter to send · Shift+Enter for new line)"
        )
        self._input.setFixedHeight(56)
        self._input.send_triggered.connect(self._send)

        self._send_btn = QPushButton("Send")
        self._send_btn.setObjectName("sendBtn")
        self._send_btn.setFixedSize(72, 56)
        self._send_btn.clicked.connect(self._send)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.setObjectName("stopBtn")
        self._stop_btn.setProperty("class", "danger")
        self._stop_btn.setFixedSize(72, 56)
        self._stop_btn.clicked.connect(self._stop)
        self._stop_btn.setVisible(False)

        row.addWidget(self._input)
        row.addWidget(self._send_btn)
        row.addWidget(self._stop_btn)
        lay.addLayout(row)

        self._status = QLabel("Ready")
        self._status.setProperty("class", "muted")
        lay.addWidget(self._status)

        return frame

    # ─── Model management ─────────────────────────────────────────────────────

    def _refresh_models(self) -> None:
        try:
            az = OllamaAnalyzer()
            resp = az.client.list()
            models = sorted(set(az._extract_model_names(resp)))
        except Exception:
            models = []

        current = self.model_combo.currentText()
        self.model_combo.clear()

        if models:
            self.model_combo.addItems(models)
            if current in models:
                self.model_combo.setCurrentText(current)
            self._status.setText(f"{len(models)} model(s) available")
        else:
            defaults = ["gemma3:4b", "qwen3:8b", "llama3.1:8b"]
            self.model_combo.addItems(defaults)
            self._status.setText("Ollama not reachable — showing defaults")

    # ─── Context management ───────────────────────────────────────────────────

    def _load_active_transcript(self) -> None:
        """Pull transcript from the Analyze tab (if a getter was provided)."""
        if self._get_transcript is None:
            self._status.setText("No transcript getter configured.")
            return
        text = self._get_transcript()
        if not text or not text.strip():
            self._status.setText("No transcript loaded in the Analyze tab yet.")
            return
        self.set_context(text, name="active transcript")

    def _browse_transcript(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Transcript File",
            str(ProjectPaths.TRANSCRIPTS_DIR),
            "Text Files (*.txt *.md);;All Files (*)",
        )
        if path:
            text = Path(path).read_text(encoding="utf-8", errors="replace")
            self.set_context(text, name=Path(path).name)

    def set_context(self, transcript: str, name: str = "transcript") -> None:
        """Inject transcript text as system-level context for the chat."""
        self._transcript_context = transcript
        chars = f"{len(transcript):,}"
        short = name if len(name) <= 42 else name[:39] + "…"
        self.context_status.setText(f"Context: {short}")
        self.context_status.setProperty("class", "ctxActive")
        self.context_status.style().unpolish(self.context_status)
        self.context_status.style().polish(self.context_status)
        self._clear_ctx_btn.setVisible(True)
        self._ctx_badge.setText(f"Transcript context active  ·  {chars} chars")
        self._ctx_badge.setVisible(True)
        self._status.setText(f"Context loaded: {chars} chars from '{short}'")

    def _clear_context(self) -> None:
        self._transcript_context = ""
        self.context_status.setText("No context")
        self.context_status.setProperty("class", "muted")
        self.context_status.style().unpolish(self.context_status)
        self.context_status.style().polish(self.context_status)
        self._clear_ctx_btn.setVisible(False)
        self._ctx_badge.setVisible(False)
        self._status.setText("Context cleared")

    # ─── Sending messages ─────────────────────────────────────────────────────

    def _send(self) -> None:
        text = self._input.toPlainText().strip()
        if not text or self._streaming:
            return

        model = self.model_combo.currentText().strip()
        if not model:
            self._status.setText("Select a model first.")
            return

        self._input.clear()
        self._append_user(text)
        self.messages.append({"role": "user", "content": text})

        # Build the message list for the worker
        payload = self._build_payload()

        self._streaming = True
        self._send_btn.setVisible(False)
        self._stop_btn.setVisible(True)
        self._status.setText("Generating…")
        self._begin_assistant_block()

        self._worker = ChatWorker(payload, model)
        self._worker.token_received.connect(self._on_token)
        self._worker.response_complete.connect(self._on_complete)
        self._worker.error_occurred.connect(self._on_error)
        self._worker.finished.connect(self._on_worker_done)
        self._worker.start()

    def _build_payload(self) -> list[dict]:
        """Assemble message list; inject system prompt on the first turn."""
        if self._transcript_context and len(self.messages) == 1:
            clamped = self._transcript_context[:_MAX_TRANSCRIPT_CHARS]
            system = {
                "role": "system",
                "content": _TRANSCRIPT_SYSTEM_TEMPLATE.format(transcript=clamped),
            }
            return [system] + list(self.messages)
        return list(self.messages)

    # ─── Display helpers ──────────────────────────────────────────────────────

    def _fmt(
        self,
        color: QColor,
        bold: bool = False,
        size_pt: int = 0,
        family: str = "",
    ) -> QTextCharFormat:
        fmt = QTextCharFormat()
        fmt.setForeground(color)
        if bold:
            fmt.setFontWeight(QFont.Weight.Bold)
        if size_pt:
            fmt.setFontPointSize(size_pt)
        if family:
            fmt.setFontFamily(family)
        return fmt

    def _cursor_at_end(self) -> QTextCursor:
        c = self._display.textCursor()
        c.movePosition(QTextCursor.MoveOperation.End)
        return c

    def _insert(self, fmt: QTextCharFormat, text: str) -> None:
        c = self._cursor_at_end()
        c.insertText(text, fmt)
        self._display.setTextCursor(c)

    def _insert_divider(self) -> None:
        """Thin horizontal rule between messages."""
        c = self._cursor_at_end()
        # Two blank lines act as visual padding; actual line drawn via blockFormat
        c.insertText("\n", self._fmt(_C_BG))
        self._display.setTextCursor(c)

    def _show_welcome(self) -> None:
        c = self._cursor_at_end()
        c.insertText(
            "\n  Subtext Chat\n",
            self._fmt(_C_USER_LABEL, bold=True, size_pt=15),
        )
        c.insertText(
            "\n  Chat with any local Ollama model. "
            "Load a transcript to ask questions\n"
            "  about your extracted content, or just talk freely.\n\n",
            self._fmt(_C_MUTED, size_pt=12),
        )
        self._display.setTextCursor(c)

    def _append_user(self, text: str) -> None:
        self._insert_divider()
        self._insert(self._fmt(_C_USER_LABEL, bold=True, size_pt=10), "  YOU\n")
        self._insert(self._fmt(_C_USER_TEXT, size_pt=13), f"  {text}\n")

    def _begin_assistant_block(self) -> None:
        self._insert(self._fmt(_C_AI_LABEL, bold=True, size_pt=10), "\n  ASSISTANT\n")
        self._insert(self._fmt(_C_AI_TEXT, size_pt=13), "  ")

    # ─── Streaming slots ──────────────────────────────────────────────────────

    def _on_token(self, token: str) -> None:
        # Replace newlines with indented newlines so output stays clean
        token = token.replace("\n", "\n  ")
        c = self._cursor_at_end()
        c.insertText(token, self._fmt(_C_AI_TEXT, size_pt=13))
        self._display.setTextCursor(c)
        self._display.ensureCursorVisible()

    def _on_complete(self, full: str) -> None:
        self.messages.append({"role": "assistant", "content": full})
        # Trailing newline for spacing
        self._insert(self._fmt(_C_AI_TEXT), "\n")
        self._status.setText("Ready")

    def _on_error(self, err: str) -> None:
        self._insert(self._fmt(_C_ERROR, size_pt=12), f"\n  Error: {err}\n")
        self._status.setText(f"Error: {err[:80]}")

    def _on_worker_done(self) -> None:
        self._streaming = False
        self._send_btn.setVisible(True)
        self._stop_btn.setVisible(False)
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    # ─── Stop / clear ─────────────────────────────────────────────────────────

    def _stop(self) -> None:
        if self._worker and self._worker.isRunning():
            self._worker.requestInterruption()
            self._worker.wait(2000)
        self._status.setText("Stopped")

    def _clear_chat(self) -> None:
        self.messages = []
        self._display.clear()
        self._show_welcome()
        self._status.setText("Chat cleared")

    # ─── Public API (called from MainWindow) ──────────────────────────────────

    def load_transcript(self, text: str, name: str = "transcript") -> None:
        """Called by MainWindow when a transcription completes."""
        self.set_context(text, name=name)
