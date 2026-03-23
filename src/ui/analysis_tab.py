"""
AI Analysis tab with responsive controls and transcript workflows.
"""
from __future__ import annotations

from typing import Optional

from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QTextEdit,
    QPushButton, QGroupBox, QComboBox, QLineEdit, QSplitter, QProgressBar,
    QTabWidget, QApplication, QMessageBox
)

from src.core.analyzer import AnalysisResult, OllamaAnalyzer
from src.ui.workers import (
    AnalysisWorker,
    CustomAnalysisWorker,
    InstallModelWorker,
    ModelTestWorker,
)


class AnalysisTab(QWidget):
    """AI Analysis tab."""
    analysis_completed = Signal(object)  # AnalysisResult

    def __init__(self):
        super().__init__()
        self.current_transcript = ""
        self.worker: Optional[AnalysisWorker] = None
        self.custom_worker: Optional[CustomAnalysisWorker] = None
        self.install_worker: Optional[InstallModelWorker] = None
        self.test_worker: Optional[ModelTestWorker] = None
        self._copy_feedback_timer = QTimer(self)
        self._copy_feedback_timer.setSingleShot(True)
        self._copy_feedback_timer.timeout.connect(self._reset_copy_button_text)
        self.setup_ui()
        self.refresh_models()
        QTimer.singleShot(100, self.check_llm_health)

    def setup_ui(self):
        """Setup the analysis tab UI."""
        layout = QVBoxLayout(self)
        layout.setSpacing(12)
        layout.setContentsMargins(12, 12, 12, 12)

        splitter = QSplitter(Qt.Vertical)

        input_section = self.create_input_section()
        splitter.addWidget(input_section)

        results_section = self.create_results_section()
        splitter.addWidget(results_section)

        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([220, 480])
        layout.addWidget(splitter)

    def create_input_section(self) -> QGroupBox:
        """Create the transcript input section."""
        group = QGroupBox("Transcript Settings")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        controls_layout = QHBoxLayout()
        model_label = QLabel("AI Model:")
        self.model_combo = QComboBox()
        self.model_combo.setMinimumWidth(190)
        self.model_combo.addItems(["gemma3:4b", "qwen3:8b", "llama3.1:8b", "llama3.2"])

        self.refresh_models_btn = QPushButton("Refresh Models")
        self.refresh_models_btn.setProperty("class", "secondary")
        self.refresh_models_btn.clicked.connect(self.refresh_models)

        self.install_model_btn = QPushButton("Install Selected")
        self.install_model_btn.setProperty("class", "secondary")
        self.install_model_btn.clicked.connect(self.install_selected_model)

        self.test_model_btn = QPushButton("Test Model")
        self.test_model_btn.setProperty("class", "secondary")
        self.test_model_btn.clicked.connect(self.test_selected_model)

        self.analyze_button = QPushButton("Analyze")
        self.analyze_button.clicked.connect(self.start_analysis)
        self.analyze_button.setEnabled(False)

        self.stop_button = QPushButton("Stop")
        self.stop_button.setProperty("class", "danger")
        self.stop_button.clicked.connect(self.stop_analysis)
        self.stop_button.setEnabled(False)

        controls_layout.addWidget(model_label)
        controls_layout.addWidget(self.model_combo)
        controls_layout.addWidget(self.refresh_models_btn)
        controls_layout.addWidget(self.install_model_btn)
        controls_layout.addWidget(self.test_model_btn)
        controls_layout.addStretch()
        controls_layout.addWidget(self.analyze_button)
        controls_layout.addWidget(self.stop_button)
        layout.addLayout(controls_layout)

        self.health_badge = QLabel("LLM: checking...")
        self.health_badge.setObjectName("llmHealthBadge")
        self.health_badge.setProperty("class", "status-info")
        layout.addWidget(self.health_badge)

        transcript_header_layout = QHBoxLayout()
        transcript_label = QLabel("Transcript:")
        transcript_label.setProperty("class", "section-title")
        transcript_header_layout.addWidget(transcript_label)
        transcript_header_layout.addStretch()

        self.copy_transcript_btn = QPushButton("Copy Transcript")
        self.copy_transcript_btn.setToolTip("Copy transcript text to clipboard")
        self.copy_transcript_btn.clicked.connect(self.copy_transcript_to_clipboard)
        self.copy_transcript_btn.setEnabled(False)

        self.clear_transcript_btn = QPushButton("Clear / New")
        self.clear_transcript_btn.setProperty("class", "secondary")
        self.clear_transcript_btn.clicked.connect(self.clear_transcript_session)
        self.clear_transcript_btn.setEnabled(False)

        transcript_header_layout.addWidget(self.copy_transcript_btn)
        transcript_header_layout.addWidget(self.clear_transcript_btn)
        layout.addLayout(transcript_header_layout)

        self.transcript_display = QTextEdit()
        self.transcript_display.setPlaceholderText("Transcript appears here after processing.")
        self.transcript_display.setMaximumHeight(180)
        self.transcript_display.setReadOnly(True)
        layout.addWidget(self.transcript_display)

        self.status_label = QLabel("Waiting for transcript...")
        self.status_label.setProperty("class", "status")
        layout.addWidget(self.status_label)

        return group

    def create_results_section(self) -> QGroupBox:
        """Create the analysis results section."""
        group = QGroupBox("AI Analysis Results")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)
        layout.addWidget(self.progress_bar)

        self.results_tabs = QTabWidget()

        self.summary_text = QTextEdit()
        self.summary_text.setPlaceholderText("AI-generated summary appears here.")
        self.summary_text.setReadOnly(True)
        self.results_tabs.addTab(self.summary_text, "Summary")

        self.quotes_text = QTextEdit()
        self.quotes_text.setPlaceholderText("Best quotes and memorable moments.")
        self.quotes_text.setReadOnly(True)
        self.results_tabs.addTab(self.quotes_text, "Quotes")

        self.topics_text = QTextEdit()
        self.topics_text.setPlaceholderText("Key topics and themes.")
        self.topics_text.setReadOnly(True)
        self.results_tabs.addTab(self.topics_text, "Topics")

        self.sentiment_text = QTextEdit()
        self.sentiment_text.setPlaceholderText("Emotional tone and sentiment analysis.")
        self.sentiment_text.setReadOnly(True)
        self.results_tabs.addTab(self.sentiment_text, "Sentiment")

        custom_widget = QWidget()
        custom_layout = QVBoxLayout(custom_widget)
        custom_layout.setSpacing(8)
        custom_input_layout = QHBoxLayout()

        self.custom_prompt = QLineEdit()
        self.custom_prompt.setPlaceholderText("Enter custom analysis prompt...")

        self.custom_analyze_button = QPushButton("Run Custom")
        self.custom_analyze_button.clicked.connect(self.run_custom_analysis)
        self.custom_analyze_button.setEnabled(False)

        self.clear_results_btn = QPushButton("Clear Results")
        self.clear_results_btn.setProperty("class", "secondary")
        self.clear_results_btn.clicked.connect(self.clear_results)

        custom_input_layout.addWidget(self.custom_prompt)
        custom_input_layout.addWidget(self.custom_analyze_button)
        custom_input_layout.addWidget(self.clear_results_btn)

        self.custom_results = QTextEdit()
        self.custom_results.setPlaceholderText("Custom analysis results.")
        self.custom_results.setReadOnly(True)

        custom_layout.addLayout(custom_input_layout)
        custom_layout.addWidget(self.custom_results)
        self.results_tabs.addTab(custom_widget, "Custom")

        layout.addWidget(self.results_tabs)
        return group

    def refresh_models(self):
        """Refresh model list from local Ollama runtime."""
        model_names = []
        try:
            analyzer = OllamaAnalyzer(self.model_combo.currentText() or "llama3.2")
            response = analyzer.client.list()
            model_names = sorted(set(analyzer._extract_model_names(response)))
        except Exception:
            model_names = []

        current = self.model_combo.currentText().strip()
        self.model_combo.clear()

        if model_names:
            self.model_combo.addItems(model_names)
            if current and current in model_names:
                self.model_combo.setCurrentText(current)
            self.status_label.setText(f"Loaded {len(model_names)} local model(s).")
            self.health_badge.setText(f"LLM: connected ({len(model_names)} model(s))")
            self.health_badge.setProperty("class", "status-success")
        else:
            fallback = ["gemma3:4b", "qwen3:8b", "llama3.1:8b", "llama3.2"]
            self.model_combo.addItems(fallback)
            if current and current in fallback:
                self.model_combo.setCurrentText(current)
            self.status_label.setText("Could not read local model list. Using defaults.")
            self.health_badge.setText("LLM: disconnected or no models")
            self.health_badge.setProperty("class", "status-error")

        self.health_badge.style().unpolish(self.health_badge)
        self.health_badge.style().polish(self.health_badge)

    def check_llm_health(self):
        """Startup health check indicator."""
        self.refresh_models()

    def install_selected_model(self):
        """Install currently selected model in background."""
        model = self.model_combo.currentText().strip()
        if not model:
            self.status_label.setText("Choose a model to install.")
            return
        if self.install_worker and self.install_worker.isRunning():
            self.status_label.setText("Model install already running.")
            return

        self.progress_bar.setVisible(True)
        self.stop_button.setEnabled(True)
        self.install_model_btn.setEnabled(False)
        self.install_worker = InstallModelWorker(model)
        self.install_worker.progress_updated.connect(self.update_status)
        self.install_worker.install_completed.connect(self.on_model_installed)
        self.install_worker.error_occurred.connect(self.on_error)
        self.install_worker.finished.connect(self.on_worker_finished)
        self.install_worker.start()

    def test_selected_model(self):
        """Run minimal test inference for selected model."""
        model = self.model_combo.currentText().strip()
        if not model:
            self.status_label.setText("Choose a model to test.")
            return
        if self.test_worker and self.test_worker.isRunning():
            self.status_label.setText("Model test already running.")
            return

        self.progress_bar.setVisible(True)
        self.stop_button.setEnabled(True)
        self.test_model_btn.setEnabled(False)
        self.test_worker = ModelTestWorker(model)
        self.test_worker.progress_updated.connect(self.update_status)
        self.test_worker.test_completed.connect(self.on_model_test_completed)
        self.test_worker.error_occurred.connect(self.on_error)
        self.test_worker.finished.connect(self.on_worker_finished)
        self.test_worker.start()

    def on_model_installed(self, installed_model: str):
        self.status_label.setText(f"Model installed: {installed_model}")
        self.refresh_models()
        self.model_combo.setCurrentText(installed_model)

    def on_model_test_completed(self, response: str):
        cleaned = (response or "").strip()
        if "MODEL_OK" in cleaned:
            self.status_label.setText("Model test passed.")
            self.health_badge.setText(f"LLM: ready ({self.model_combo.currentText()})")
            self.health_badge.setProperty("class", "status-success")
        else:
            preview = cleaned[:120] + ("..." if len(cleaned) > 120 else "")
            self.status_label.setText(f"Model responded (non-standard): {preview}")
            self.health_badge.setText(f"LLM: responding ({self.model_combo.currentText()})")
            self.health_badge.setProperty("class", "status-info")

        self.health_badge.style().unpolish(self.health_badge)
        self.health_badge.style().polish(self.health_badge)

    def load_transcript(self, transcript: str):
        """Load transcript for analysis."""
        self.current_transcript = transcript
        self.transcript_display.setPlainText(transcript)
        self.analyze_button.setEnabled(True)
        self.custom_analyze_button.setEnabled(True)
        self.copy_transcript_btn.setEnabled(True)
        self.clear_transcript_btn.setEnabled(True)
        self.status_label.setText(f"Transcript loaded ({len(transcript):,} characters). Ready for analysis.")

    def copy_transcript_to_clipboard(self):
        """Copy transcript text to clipboard and show quick button feedback."""
        if not self.current_transcript:
            self.status_label.setText("No transcript to copy.")
            return

        QApplication.clipboard().setText(self.current_transcript)
        self.copy_transcript_btn.setText("Copied")
        self.status_label.setText(f"Transcript copied ({len(self.current_transcript):,} characters).")
        self._copy_feedback_timer.start(1800)

    def _reset_copy_button_text(self):
        self.copy_transcript_btn.setText("Copy Transcript")

    def clear_transcript_session(self, confirm: bool = True):
        """Clear transcript and analysis output for a new run."""
        if confirm:
            should_clear = QMessageBox.question(
                self,
                "Clear Transcript Session",
                "Clear the current transcript and all analysis results?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if should_clear != QMessageBox.StandardButton.Yes:
                return

        self.stop_analysis()
        self.current_transcript = ""
        self.transcript_display.clear()
        self.custom_prompt.clear()
        self.clear_results()
        self.analyze_button.setEnabled(False)
        self.custom_analyze_button.setEnabled(False)
        self.copy_transcript_btn.setEnabled(False)
        self.clear_transcript_btn.setEnabled(False)
        self.status_label.setText("Session cleared. Load or create a new transcript.")

    def start_analysis(self):
        """Start AI analysis."""
        if not self.current_transcript:
            self.status_label.setText("No transcript available.")
            return

        if self.worker and self.worker.isRunning():
            self.status_label.setText("Analysis already running.")
            return

        self.clear_results()
        self.progress_bar.setVisible(True)
        self.analyze_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        model = self.model_combo.currentText().strip()
        self.worker = AnalysisWorker(self.current_transcript, model)
        self.worker.progress_updated.connect(self.update_status)
        self.worker.analysis_completed.connect(self.on_analysis_completed)
        self.worker.error_occurred.connect(self.on_error)
        self.worker.finished.connect(self.on_worker_finished)
        self.worker.start()

    def stop_analysis(self):
        """Stop current analysis workers."""
        if self.worker and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait(3000)

        if self.custom_worker and self.custom_worker.isRunning():
            self.custom_worker.terminate()
            self.custom_worker.wait(3000)

        if self.install_worker and self.install_worker.isRunning():
            self.install_worker.terminate()
            self.install_worker.wait(3000)

        if self.test_worker and self.test_worker.isRunning():
            self.test_worker.terminate()
            self.test_worker.wait(3000)

        self.on_worker_finished()

    def run_custom_analysis(self):
        """Run custom analysis with a user prompt."""
        prompt = self.custom_prompt.text().strip()
        if not prompt or not self.current_transcript:
            self.status_label.setText("Enter a custom prompt and ensure transcript is loaded.")
            return

        if self.custom_worker and self.custom_worker.isRunning():
            self.status_label.setText("Custom analysis already running.")
            return

        self.progress_bar.setVisible(True)
        self.custom_analyze_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.custom_results.clear()

        model = self.model_combo.currentText().strip()
        self.custom_worker = CustomAnalysisWorker(self.current_transcript, model, prompt)
        self.custom_worker.progress_updated.connect(self.update_status)
        self.custom_worker.analysis_completed.connect(self.on_custom_analysis_completed)
        self.custom_worker.error_occurred.connect(self.on_error)
        self.custom_worker.finished.connect(self.on_worker_finished)
        self.custom_worker.start()

    def on_custom_analysis_completed(self, content: str):
        self.custom_results.setPlainText(content)
        self.results_tabs.setCurrentIndex(self.results_tabs.indexOf(self.custom_results.parentWidget()))

    def update_status(self, message: str):
        """Update status message."""
        self.status_label.setText(message)

    def clear_results(self):
        """Clear all result displays."""
        self.summary_text.clear()
        self.quotes_text.clear()
        self.topics_text.clear()
        self.sentiment_text.clear()
        self.custom_results.clear()

    def on_analysis_completed(self, result: AnalysisResult):
        """Handle analysis completion."""
        self.summary_text.setPlainText(result.summary)

        if result.quotes:
            quotes_formatted = "\n\n".join([f'- "{quote}"' for quote in result.quotes])
            self.quotes_text.setPlainText(quotes_formatted)
        else:
            self.quotes_text.setPlainText("No quotes extracted.")

        if result.topics:
            topics_formatted = "\n".join([f"- {topic}" for topic in result.topics])
            self.topics_text.setPlainText(topics_formatted)
        else:
            self.topics_text.setPlainText("No topics identified.")

        self.sentiment_text.setPlainText(result.sentiment)
        self.status_label.setText("Analysis completed successfully.")
        self.analysis_completed.emit(result)

    def on_error(self, error_message: str):
        """Handle analysis error."""
        self.status_label.setText(f"Error: {error_message}")

    def on_worker_finished(self):
        """Handle worker completion."""
        self.progress_bar.setVisible(False)
        self.analyze_button.setEnabled(bool(self.current_transcript))
        self.custom_analyze_button.setEnabled(bool(self.current_transcript))
        self.install_model_btn.setEnabled(True)
        self.test_model_btn.setEnabled(True)
        self.stop_button.setEnabled(False)

        if self.worker:
            self.worker.deleteLater()
            self.worker = None

        if self.custom_worker:
            self.custom_worker.deleteLater()
            self.custom_worker = None

        if self.install_worker:
            self.install_worker.deleteLater()
            self.install_worker = None

        if self.test_worker:
            self.test_worker.deleteLater()
            self.test_worker = None
