"""
Main application window — sidebar navigation, stacked content area.
"""
from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSpacerItem,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.config.paths import ProjectPaths
from src.ui.analysis_tab import AnalysisTab
from src.ui.chat_tab import ChatTab
from src.ui.download_tab import DownloadTab
from src.ui.results_tab import ResultsTab
from src.ui.styles import DARK_THEME


class MainWindow(QMainWindow):
    """Main app shell with a fixed sidebar and stacked content pages."""

    def __init__(self):
        super().__init__()
        ProjectPaths.initialize()
        self._setup_ui()
        self._setup_theme()

    # ─── UI construction ──────────────────────────────────────────────────────

    def _setup_ui(self) -> None:
        self.setWindowTitle("Subtext")
        self.setMinimumSize(980, 660)
        self.resize(1200, 800)

        central = QWidget()
        self.setCentralWidget(central)

        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ───────────────────────────────────────────────────────────
        self._sidebar = self._build_sidebar()
        root.addWidget(self._sidebar)

        # ── Content stack ─────────────────────────────────────────────────────
        self._stack = QStackedWidget()

        self.download_tab = DownloadTab()
        self.analysis_tab = AnalysisTab()
        self.results_tab = ResultsTab()
        self.chat_tab = ChatTab(
            get_transcript_fn=lambda: self.analysis_tab.current_transcript
        )

        self._stack.addWidget(self.download_tab)   # 0 – Transcribe
        self._stack.addWidget(self.analysis_tab)   # 1 – Analyze
        self._stack.addWidget(self.results_tab)    # 2 – Results
        self._stack.addWidget(self.chat_tab)       # 3 – Chat

        root.addWidget(self._stack, stretch=1)

        self._switch_page(0)
        self._setup_connections()

    def _build_sidebar(self) -> QFrame:
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        sidebar.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)

        lay = QVBoxLayout(sidebar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        # ── Logo block ────────────────────────────────────────────────────────
        logo_frame = QWidget()
        logo_lay = QVBoxLayout(logo_frame)
        logo_lay.setContentsMargins(16, 20, 16, 18)
        logo_lay.setSpacing(2)

        title = QLabel("Subtext")
        title.setObjectName("appTitle")

        subtitle = QLabel("local media intelligence")
        subtitle.setObjectName("appSubtitle")

        logo_lay.addWidget(title)
        logo_lay.addWidget(subtitle)
        lay.addWidget(logo_frame)

        # ── Thin rule ─────────────────────────────────────────────────────────
        lay.addWidget(self._hr())

        # ── Nav section ───────────────────────────────────────────────────────
        nav_header = QLabel("WORKSPACE")
        nav_header.setObjectName("sidebarSectionLabel")
        nav_header.setContentsMargins(16, 14, 0, 6)
        lay.addWidget(nav_header)

        self._nav_buttons: list[QPushButton] = []
        nav_items = [
            ("Transcribe", 0, "Download & transcribe media"),
            ("Analyze",    1, "AI analysis of transcripts"),
            ("Results",    2, "Export & review results"),
            ("Chat",       3, "Chat with a local LLM"),
        ]
        for label, idx, tip in nav_items:
            btn = QPushButton(label)
            btn.setObjectName("navBtn")
            btn.setToolTip(tip)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(lambda _=False, i=idx: self._switch_page(i))
            self._nav_buttons.append(btn)
            lay.addWidget(btn)

        lay.addSpacerItem(QSpacerItem(0, 12, QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed))
        lay.addWidget(self._hr())

        # ── Quick actions ─────────────────────────────────────────────────────
        actions_header = QLabel("QUICK ACCESS")
        actions_header.setObjectName("sidebarSectionLabel")
        actions_header.setContentsMargins(16, 14, 0, 6)
        lay.addWidget(actions_header)

        quick_actions = [
            ("New Session",      self._reset_session),
            ("Open Videos",      lambda: self.download_tab.open_folder(ProjectPaths.VIDEOS_DIR)),
            ("Open Transcripts", lambda: self.download_tab.open_folder(ProjectPaths.TRANSCRIPTS_DIR)),
        ]
        for label, fn in quick_actions:
            btn = QPushButton(label)
            btn.setObjectName("sidebarAction")
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.clicked.connect(fn)
            lay.addWidget(btn)

        # ── Footer ────────────────────────────────────────────────────────────
        lay.addStretch()
        lay.addWidget(self._hr())

        footer = QWidget()
        footer_lay = QHBoxLayout(footer)
        footer_lay.setContentsMargins(16, 10, 16, 14)

        ver = QLabel("v1.0.0")
        ver.setObjectName("version")
        footer_lay.addWidget(ver)
        footer_lay.addStretch()
        lay.addWidget(footer)

        return sidebar

    @staticmethod
    def _hr() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setProperty("class", "divider")
        return line

    # ─── Navigation ───────────────────────────────────────────────────────────

    def _switch_page(self, index: int) -> None:
        self._stack.setCurrentIndex(index)
        for i, btn in enumerate(self._nav_buttons):
            active = (i == index)
            btn.setProperty("active", "true" if active else "false")
            btn.style().unpolish(btn)
            btn.style().polish(btn)
            btn.update()

    # ─── Cross-tab signals ────────────────────────────────────────────────────

    def _setup_connections(self) -> None:
        self.download_tab.transcription_completed.connect(self._on_transcription_done)
        self.analysis_tab.analysis_completed.connect(self._on_analysis_done)

    def _on_transcription_done(self, path: Path, text: str) -> None:
        """Transcription finished → load into Analyze tab and navigate there."""
        self.analysis_tab.load_transcript(text)
        self._switch_page(1)

    def _on_analysis_done(self, result) -> None:
        """Analysis finished → load into Results tab and navigate there."""
        self.results_tab.load_results(result)
        self._switch_page(2)

    def _reset_session(self) -> None:
        self.analysis_tab.clear_transcript_session(confirm=False)
        self.results_tab.clear_results()
        self._switch_page(0)

    # ─── Theme ────────────────────────────────────────────────────────────────

    def _setup_theme(self) -> None:
        self.setStyleSheet(DARK_THEME)
        font = QFont("Segoe UI", 10)
        self.setFont(font)
        QApplication.instance().setFont(font)


# ─── App bootstrap ────────────────────────────────────────────────────────────

def create_app() -> QApplication:
    app = QApplication(sys.argv)
    app.setApplicationName("Subtext")
    app.setApplicationVersion("1.0.0")
    app.setOrganizationName("Subtext")
    return app


def main() -> None:
    app = create_app()
    window = MainWindow()
    window.show()

    screen = app.primaryScreen().geometry()
    geo = window.geometry()
    window.move(
        (screen.width() - geo.width()) // 2,
        (screen.height() - geo.height()) // 2,
    )
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
