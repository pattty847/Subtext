"""
Download and transcription tab with batch-aware workflows.
"""
from __future__ import annotations

import html
import os
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QProgressBar, QTextEdit, QFrame, QFileDialog, QComboBox
)

from src.config.paths import ProjectPaths
from src.core.input_processor import InputProcessor
from src.ui.widgets import MultiSelectDropdown
from src.ui.workers import DownloadWorker


class DownloadTab(QWidget):
    """Download and transcription tab."""
    transcription_completed = Signal(Path, str)  # (file_path, transcript_text)
    FFMPEG_DOWNLOAD_URL = "https://www.ffmpeg.org/download.html"

    def __init__(self):
        super().__init__()
        self.worker: Optional[DownloadWorker] = None
        self._expected_items = 0
        self._download_only_mode = False
        self._completed_outputs: list[tuple[Path, str]] = []
        self.setup_ui()

    def setup_ui(self):
        """Setup the download tab UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        layout.addWidget(self.create_input_section())

        divider1 = QFrame()
        divider1.setFrameShape(QFrame.Shape.HLine)
        divider1.setProperty("class", "divider")
        layout.addWidget(divider1)

        layout.addWidget(self.create_progress_section())

        divider2 = QFrame()
        divider2.setFrameShape(QFrame.Shape.HLine)
        divider2.setProperty("class", "divider")
        layout.addWidget(divider2)

        layout.addWidget(self.create_log_section(), stretch=1)

    def create_input_section(self) -> QWidget:
        """Create the source input section."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(10)
        layout.setContentsMargins(0, 0, 0, 0)

        url_layout = QHBoxLayout()
        self.browse_btn = QPushButton("Browse")
        self.browse_btn.setFixedWidth(120)
        self.browse_btn.setProperty("class", "secondary")
        self.browse_btn.clicked.connect(self.on_browse_clicked)

        self.url_input = QLineEdit()
        self.url_input.setPlaceholderText(
            "Enter URL(s) and/or local media files (separate with semicolons or new lines)"
        )
        self.url_input.returnPressed.connect(self.start_process)
        self.url_input.textChanged.connect(self.on_input_changed)
        self.url_input.setToolTip(
            "Mix URLs and local files in one run. Example: https://...; C:/video.mp4"
        )
        url_layout.addWidget(self.browse_btn)
        url_layout.addWidget(self.url_input, stretch=1)
        layout.addLayout(url_layout)

        self.validation_label = QLabel("")
        self.validation_label.setObjectName("validation")
        layout.addWidget(self.validation_label)

        settings_layout = QHBoxLayout()
        settings_layout.addStretch()

        self.model_combo = QComboBox()
        combo_font = QFont(self.model_combo.font())
        combo_font.setPointSize(10)
        self.model_combo.setFont(combo_font)
        self.model_combo.addItems(["tiny.en", "base.en", "small.en", "medium.en", "large-v3", "large-v3-turbo"])
        self.model_combo.setCurrentText("small.en")
        self.model_combo.setMinimumWidth(150)
        if self.model_combo.view():
            self.model_combo.view().setFont(combo_font)

        self.options_dropdown = MultiSelectDropdown()
        self.options_dropdown.setFont(combo_font)
        self.options_dropdown.setMinimumWidth(220)
        self.options_dropdown.option_changed.connect(self.on_option_changed)

        settings_layout.addWidget(self.model_combo)
        settings_layout.addWidget(self.options_dropdown)
        settings_layout.addStretch()
        layout.addLayout(settings_layout)

        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)
        button_layout.addStretch()

        self.start_button = QPushButton("Start")
        self.start_button.setMinimumWidth(90)
        self.start_button.clicked.connect(self.start_process)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setMinimumWidth(90)
        self.stop_button.setProperty("class", "danger")
        self.stop_button.clicked.connect(self.stop_process)
        self.stop_button.setEnabled(False)

        self.videos_button = QPushButton("Videos")
        self.videos_button.setMinimumWidth(90)
        self.videos_button.setProperty("class", "secondary")
        self.videos_button.clicked.connect(lambda: self.open_folder(ProjectPaths.VIDEOS_DIR))

        self.transcripts_button = QPushButton("Transcripts")
        self.transcripts_button.setMinimumWidth(90)
        self.transcripts_button.setProperty("class", "secondary")
        self.transcripts_button.clicked.connect(lambda: self.open_folder(ProjectPaths.TRANSCRIPTS_DIR))

        button_layout.addWidget(self.start_button)
        button_layout.addWidget(self.stop_button)
        button_layout.addWidget(self.videos_button)
        button_layout.addWidget(self.transcripts_button)
        button_layout.addStretch()
        layout.addLayout(button_layout)
        return widget

    def create_progress_section(self) -> QWidget:
        """Create progress section."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(8)
        layout.setContentsMargins(0, 0, 0, 0)

        queue_label = QLabel("Processing Queue")
        queue_label.setProperty("class", "section-title")
        layout.addWidget(queue_label)

        self.queue_list = QTextEdit()
        self.queue_list.setMaximumHeight(96)
        self.queue_list.setReadOnly(True)
        self.queue_list.setObjectName("queue")
        layout.addWidget(self.queue_list)

        download_layout = QHBoxLayout()
        download_label = QLabel("Download:")
        download_label.setMinimumWidth(100)
        self.download_progress = QProgressBar()
        self.download_progress.setVisible(False)
        download_layout.addWidget(download_label)
        download_layout.addWidget(self.download_progress)
        layout.addLayout(download_layout)

        transcription_layout = QHBoxLayout()
        transcription_label = QLabel("Transcription:")
        transcription_label.setMinimumWidth(100)
        self.transcription_progress = QProgressBar()
        self.transcription_progress.setVisible(False)
        transcription_layout.addWidget(transcription_label)
        transcription_layout.addWidget(self.transcription_progress)
        layout.addLayout(transcription_layout)

        self.status_label = QLabel("Ready to start.")
        self.status_label.setWordWrap(True)
        self.status_label.setProperty("class", "status")
        layout.addWidget(self.status_label)

        self.install_help_label = QLabel("")
        self.install_help_label.setWordWrap(True)
        self.install_help_label.setOpenExternalLinks(True)
        self.install_help_label.setTextFormat(Qt.TextFormat.RichText)
        self.install_help_label.setVisible(False)
        layout.addWidget(self.install_help_label)
        return widget

    def create_log_section(self) -> QWidget:
        """Create log section."""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setSpacing(6)
        layout.setContentsMargins(0, 0, 0, 0)

        header_layout = QHBoxLayout()
        log_label = QLabel("Process Log")
        log_label.setProperty("class", "section-title")
        clear_btn = QPushButton("Clear Log")
        clear_btn.setProperty("class", "secondary")
        clear_btn.clicked.connect(lambda: self.log_output.clear())
        header_layout.addWidget(log_label)
        header_layout.addStretch()
        header_layout.addWidget(clear_btn)
        layout.addLayout(header_layout)

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setObjectName("log")
        layout.addWidget(self.log_output)
        return widget

    def start_process(self):
        """Start the download/transcribe process."""
        input_text = self.url_input.text().strip()
        if not input_text:
            self.add_log("Please enter at least one URL or local file.")
            return

        items = InputProcessor.parse_mixed_input(input_text)
        total_items = len(items["urls"]) + len(items["files"])
        if total_items == 0:
            self.add_log("No valid URLs/files found in input.")
            return
        if self.worker and self.worker.isRunning():
            self.add_log("A process is already running.")
            return

        model = self.model_combo.currentText()
        download_only = self.options_dropdown.get_download_only()
        keep_video = self.options_dropdown.get_retain_video()
        copy_files = self.options_dropdown.get_copy_to_assets()
        youtube_captions_first = self.options_dropdown.get_youtube_captions_first()
        use_browser_cookies = self.options_dropdown.get_use_browser_cookies()

        queue_items = []
        for url in items["urls"]:
            queue_items.append({"source": url, "status": "pending", "type": "url"})
        for file_path in items["files"]:
            queue_items.append({"source": file_path, "status": "pending", "type": "file"})
        self.update_queue_display(queue_items)

        self.download_progress.setValue(0)
        self.transcription_progress.setValue(0)
        self.download_progress.setVisible(True)
        self.transcription_progress.setVisible(not download_only)
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.log_output.clear()

        self._completed_outputs = []
        self._expected_items = total_items
        self._download_only_mode = download_only

        self.worker = DownloadWorker(
            input_text,
            model,
            download_only,
            keep_video,
            copy_files,
            youtube_captions_first,
            use_browser_cookies,
        )
        self.worker.progress_updated.connect(self.update_status)
        self.worker.download_progress.connect(self.download_progress.setValue)
        self.worker.transcription_progress.connect(self.transcription_progress.setValue)
        self.worker.completed.connect(self.on_completed)
        self.worker.batch_completed.connect(self.on_batch_completed)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()
        self.add_log(f"Starting process for {total_items} item(s).")

    def update_queue_display(self, items: list[dict]):
        """Update queue display."""
        queue_text = []
        for i, item in enumerate(items, 1):
            source = item.get("source", "")
            status = item.get("status", "pending")
            status_icon = {
                "pending": "[]",
                "downloading": "[D]",
                "copying": "[C]",
                "transcribing": "[T]",
                "completed": "[OK]",
                "error": "[X]",
            }.get(status, "[]")

            try:
                path = Path(source)
                display_name = path.name if path.exists() and path.is_file() else source
            except Exception:
                display_name = source

            if len(display_name) > 72:
                display_name = display_name[:69] + "..."
            queue_text.append(f"{i}. {status_icon} {display_name}")

        self.queue_list.setPlainText("\n".join(queue_text))

    def stop_process(self):
        """Stop current process."""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(3000)
        elif self.worker:
            self.worker.wait(1000)

        self.on_worker_finished()
        self.add_log("Process stopped by user.")

    def update_status(self, message: str):
        """Update status text and log."""
        self.status_label.setText(message)
        self.install_help_label.setVisible(False)
        self.install_help_label.clear()
        lowered = message.lower()
        if "error" in lowered:
            self.status_label.setProperty("class", "status-error")
        elif "completed" in lowered:
            self.status_label.setProperty("class", "status-success")
        elif "processing" in lowered or "download" in lowered or "transcrib" in lowered:
            self.status_label.setProperty("class", "status-info")
        else:
            self.status_label.setProperty("class", "status")
        self.add_log(message)

    def add_log(self, message: str):
        """Add line to process log."""
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_output.append(f"[{stamp}] {message}")

    def on_option_changed(self, option_name: str, checked: bool):
        """Keep options internally consistent."""
        if option_name == "Download Only" and checked and not self.options_dropdown.get_retain_video():
            self.options_dropdown.options["Retain Video"] = True
            self.options_dropdown.update_display()
            menu = self.options_dropdown.menu()
            if menu:
                for action in menu.actions():
                    widget = action.defaultWidget()
                    if isinstance(widget, QPushButton) and widget.text() == "Retain Video":
                        widget.setChecked(True)

    def on_completed(self, file_path: Path, transcript_text: str):
        """Handle per-item completion events."""
        self._completed_outputs.append((file_path, transcript_text))
        if transcript_text:
            self.add_log(f"Transcript saved: {file_path} ({len(transcript_text):,} chars)")
        else:
            self.add_log(f"Download saved: {file_path}")

        current_text = self.queue_list.toPlainText()
        if current_text:
            lines = current_text.split("\n")
            updated = []
            upgraded = False
            for line in lines:
                if not upgraded and ("[]" in line or "[D]" in line or "[C]" in line or "[T]" in line):
                    updated.append(line.replace("[]", "[OK]").replace("[D]", "[OK]").replace("[C]", "[OK]").replace("[T]", "[OK]"))
                    upgraded = True
                else:
                    updated.append(line)
            self.queue_list.setPlainText("\n".join(updated))

    def on_batch_completed(self, completed_items: list[tuple[Path, str]]):
        """Handle batch completion event."""
        if not completed_items:
            return

        if self._download_only_mode:
            self.status_label.setText(f"Completed {len(completed_items)}/{self._expected_items} download item(s).")
            self.status_label.setProperty("class", "status-success")
            return

        transcript_items = [(path, text) for path, text in completed_items if text]
        if not transcript_items:
            return

        if len(transcript_items) == 1:
            path, text = transcript_items[0]
            self.status_label.setText(f"Transcription completed: {path.name}")
            self.status_label.setProperty("class", "status-success")
            self.transcription_completed.emit(path, text)
            return

        sections = [f"[Item {idx}] {path.name}\n{text}" for idx, (path, text) in enumerate(transcript_items, 1)]
        combined_text = ("\n\n" + ("-" * 60) + "\n\n").join(sections)
        combined_path = ProjectPaths.TRANSCRIPTS_DIR / "batch_combined_transcript.txt"
        combined_path.write_text(combined_text, encoding="utf-8")
        self.status_label.setText(
            f"Batch completed ({len(transcript_items)} transcripts). Combined transcript loaded for analysis."
        )
        self.status_label.setProperty("class", "status-success")
        self.add_log(f"Combined transcript written to {combined_path}")
        self.transcription_completed.emit(combined_path, combined_text)

    def open_folder(self, folder_path: Path):
        """Open folder in system file explorer."""
        path_str = str(folder_path.resolve())
        if platform.system() == "Windows":
            os.startfile(path_str)
        elif platform.system() == "Darwin":
            os.system(f"open '{path_str}'")
        else:
            os.system(f"xdg-open '{path_str}'")

    def on_error(self, error_message: str):
        """Handle worker errors."""
        self.add_log(f"Error: {error_message}")
        self.status_label.setText(f"Error: {error_message}")
        self.status_label.setProperty("class", "status-error")

        if self._is_ffmpeg_error(error_message):
            escaped_url = html.escape(self.FFMPEG_DOWNLOAD_URL, quote=True)
            self.install_help_label.setText(
                f"FFmpeg is required for transcription. "
                f"<a href=\"{escaped_url}\">Click here to download/install FFmpeg.</a>"
            )
            self.install_help_label.setVisible(True)
            self.add_log(f"Install FFmpeg: {self.FFMPEG_DOWNLOAD_URL}")

        current_text = self.queue_list.toPlainText()
        if current_text:
            lines = current_text.split("\n")
            updated = []
            for line in lines:
                if "[]" in line or "[D]" in line or "[C]" in line or "[T]" in line:
                    updated.append(line.replace("[]", "[X]").replace("[D]", "[X]").replace("[C]", "[X]").replace("[T]", "[X]"))
                else:
                    updated.append(line)
            self.queue_list.setPlainText("\n".join(updated))

    @staticmethod
    def _is_ffmpeg_error(error_message: str) -> bool:
        lowered = error_message.lower()
        return "ffmpeg" in lowered or "ffprobe" in lowered

    def on_worker_finished(self):
        """Cleanup worker state after process finishes."""
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        if not self.status_label.text().strip():
            self.status_label.setText("Ready for next task.")
            self.status_label.setProperty("class", "status")
        if self.worker:
            self.worker.deleteLater()
            self.worker = None

    def on_browse_clicked(self):
        """Open file picker for multiple media files."""
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "Select Media Files",
            str(Path.home()),
            "Media Files (*.mp4 *.avi *.mov *.mkv *.webm *.flv *.wmv *.m4v *.3gp *.mp3 *.wav *.m4a *.flac *.aac *.ogg *.opus *.wma *.aiff *.aif);;All Files (*)",
        )
        if files:
            self.handle_selected_files(files)

    def handle_selected_files(self, file_paths: list[str]):
        """Append selected files to existing input."""
        current_text = self.url_input.text().strip()
        file_text = "; ".join(file_paths)
        combined_text = f"{current_text}; {file_text}" if current_text else file_text
        self.url_input.setText(combined_text)
        self.on_input_changed()

    def on_input_changed(self):
        """Validate mixed input continuously."""
        input_text = self.url_input.text().strip()
        if not input_text:
            self.validation_label.setText("")
            return

        items = InputProcessor.parse_mixed_input(input_text)
        total_items = len(items["urls"]) + len(items["files"])
        invalid_items = len(items["invalid"])

        if invalid_items > 0:
            self.validation_label.setText(f"{invalid_items} invalid input(s) detected")
            self.validation_label.setProperty("class", "validation-error")
        elif total_items > 0:
            url_count = len(items["urls"])
            file_count = len(items["files"])
            if url_count > 0 and file_count > 0:
                self.validation_label.setText(f"{url_count} URL(s), {file_count} local file(s) ready")
            elif url_count > 0:
                self.validation_label.setText(f"{url_count} URL(s) ready")
            else:
                self.validation_label.setText(f"{file_count} local file(s) ready")
            self.validation_label.setProperty("class", "validation-success")
        else:
            self.validation_label.setText("")
            self.validation_label.setProperty("class", "")
