"""
Modern dark theme for Subtext — thin lines, teal accent, near-black palette.
"""

DARK_THEME = """
/* ═══════════════════════════════════════════════════════
   BASE
═══════════════════════════════════════════════════════ */
QMainWindow, QDialog {
    background-color: #0f0f11;
    color: #e8e8ea;
}

QWidget {
    color: #e8e8ea;
    font-size: 13px;
}

/* ═══════════════════════════════════════════════════════
   SIDEBAR NAVIGATION
═══════════════════════════════════════════════════════ */
QFrame#sidebar {
    background-color: #0c0c0e;
    border-right: 1px solid #1c1c1f;
    border-radius: 0px;
}

QLabel#appTitle {
    font-size: 17px;
    font-weight: 700;
    color: #14b8a6;
    letter-spacing: -0.5px;
}

QLabel#appSubtitle {
    font-size: 11px;
    color: #3a3a3f;
    letter-spacing: 0.2px;
}

QPushButton#navBtn {
    background: transparent;
    color: #4a4a52;
    border: none;
    border-left: 2px solid transparent;
    border-radius: 0px;
    padding: 10px 16px 10px 14px;
    text-align: left;
    font-size: 13px;
    font-weight: 500;
    min-width: 140px;
}

QPushButton#navBtn:hover {
    background: #141416;
    color: #a0a0a8;
    border-left: 2px solid transparent;
}

QPushButton#navBtn[active="true"] {
    background: #0d1f1e;
    color: #14b8a6;
    border-left: 2px solid #14b8a6;
    font-weight: 600;
}

QLabel#sidebarSectionLabel {
    font-size: 10px;
    font-weight: 600;
    color: #2a2a2f;
    letter-spacing: 1.2px;
    padding: 0 16px;
}

QPushButton#sidebarAction {
    background: transparent;
    color: #3a3a42;
    border: none;
    border-radius: 0px;
    padding: 7px 16px 7px 16px;
    text-align: left;
    font-size: 11px;
    min-width: 140px;
}

QPushButton#sidebarAction:hover {
    background: #141416;
    color: #6a6a72;
}

/* ═══════════════════════════════════════════════════════
   LINE EDITS
═══════════════════════════════════════════════════════ */
QLineEdit {
    background: #17171a;
    border: 1px solid #26262b;
    border-radius: 6px;
    padding: 8px 12px;
    color: #e8e8ea;
    font-size: 13px;
    selection-background-color: #14b8a6;
    selection-color: #000;
}

QLineEdit:hover {
    border-color: #32323a;
}

QLineEdit:focus {
    border: 1px solid #14b8a6;
    background: #191921;
    outline: none;
}

QLineEdit:disabled {
    background: #131315;
    color: #3a3a40;
    border-color: #1e1e22;
}

/* ═══════════════════════════════════════════════════════
   TEXT EDITS
═══════════════════════════════════════════════════════ */
QTextEdit {
    background: #111113;
    border: 1px solid #222228;
    border-radius: 6px;
    padding: 10px 12px;
    font-family: "SF Mono", "Consolas", "Fira Code", monospace;
    font-size: 12px;
    color: #dcdce0;
    line-height: 1.6;
    selection-background-color: #14b8a6;
    selection-color: #000;
}

QTextEdit:focus {
    border-color: #2e2e36;
}

QTextEdit#queue {
    background: #111113;
    border: 1px solid #1e1e24;
    font-size: 11px;
    padding: 8px 12px;
    color: #8888a0;
}

QTextEdit#log {
    background: #0d0d0f;
    border: 1px solid #1a1a1f;
    font-size: 11px;
    color: #888890;
}

QTextEdit#chatDisplay {
    background: #0f0f11;
    border: none;
    padding: 20px 24px;
    font-family: "Segoe UI", "SF Pro Text", system-ui, sans-serif;
    font-size: 13px;
    color: #e8e8ea;
    line-height: 1.7;
}

QTextEdit#chatTextInput {
    background: #17171a;
    border: 1px solid #26262b;
    border-radius: 8px;
    padding: 10px 14px;
    font-family: "Segoe UI", system-ui, sans-serif;
    font-size: 13px;
    color: #e8e8ea;
    line-height: 1.5;
}

QTextEdit#chatTextInput:focus {
    border-color: #14b8a6;
}

/* ═══════════════════════════════════════════════════════
   BUTTONS
═══════════════════════════════════════════════════════ */
QPushButton {
    background: #14b8a6;
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    font-weight: 600;
    min-height: 16px;
}

QPushButton:hover {
    background: #0d9488;
}

QPushButton:pressed {
    background: #0b7a6e;
}

QPushButton:disabled {
    background: #1e1e22;
    color: #3a3a42;
    border: 1px solid #222228;
}

QPushButton.secondary {
    background: #1a1a1e;
    color: #8888a0;
    border: 1px solid #26262b;
}

QPushButton.secondary:hover {
    background: #222228;
    color: #c0c0c8;
    border-color: #32323a;
}

QPushButton.secondary:pressed {
    background: #141418;
}

QPushButton.secondary:disabled {
    background: #141418;
    color: #2e2e36;
    border-color: #1e1e24;
}

QPushButton.danger {
    background: #3f0f0f;
    color: #f87171;
    border: 1px solid #5a1515;
}

QPushButton.danger:hover {
    background: #521414;
    color: #fca5a5;
    border-color: #7a1f1f;
}

QPushButton.danger:pressed {
    background: #2d0a0a;
}

QPushButton.multi-select {
    background: #17171a;
    border: 1px solid #26262b;
    color: #8888a0;
    text-align: left;
    padding: 9px 12px;
}

QPushButton.multi-select:hover {
    border-color: #32323a;
    color: #c0c0c8;
}

/* Send button special */
QPushButton#sendBtn {
    background: #14b8a6;
    color: #fff;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
}

QPushButton#sendBtn:hover { background: #0d9488; }
QPushButton#sendBtn:pressed { background: #0b7a6e; }

QPushButton#stopBtn {
    background: #3f0f0f;
    color: #f87171;
    border: 1px solid #5a1515;
    border-radius: 8px;
    font-size: 13px;
    font-weight: 700;
}

QPushButton#stopBtn:hover {
    background: #521414;
    color: #fca5a5;
}

/* ═══════════════════════════════════════════════════════
   COMBO BOX
═══════════════════════════════════════════════════════ */
QComboBox {
    background: #17171a;
    border: 1px solid #26262b;
    border-radius: 6px;
    padding: 7px 10px;
    color: #e8e8ea;
    font-size: 13px;
    min-height: 16px;
}

QComboBox:hover {
    border-color: #32323a;
}

QComboBox:focus {
    border-color: #14b8a6;
    outline: none;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox::down-arrow {
    image: none;
    border-left: 4px solid transparent;
    border-right: 4px solid transparent;
    border-top: 5px solid #555560;
    margin-right: 8px;
}

QComboBox QAbstractItemView {
    background: #1a1a1e;
    border: 1px solid #26262b;
    border-radius: 6px;
    selection-background-color: #14b8a6;
    selection-color: #000;
    color: #e8e8ea;
    padding: 4px;
    outline: none;
}

/* ═══════════════════════════════════════════════════════
   PROGRESS BAR
═══════════════════════════════════════════════════════ */
QProgressBar {
    background: #17171a;
    border: 1px solid #26262b;
    border-radius: 3px;
    height: 4px;
    text-align: center;
    color: transparent;
    font-size: 1px;
}

QProgressBar::chunk {
    background: #14b8a6;
    border-radius: 3px;
}

/* ═══════════════════════════════════════════════════════
   LABELS
═══════════════════════════════════════════════════════ */
QLabel {
    color: #c0c0c8;
    font-size: 13px;
    background: transparent;
}

QLabel.section-title {
    font-size: 11px;
    font-weight: 700;
    color: #55555e;
    letter-spacing: 0.8px;
    text-transform: uppercase;
}

QLabel.fieldLabel {
    font-size: 12px;
    color: #55555e;
    font-weight: 500;
}

QLabel.muted {
    color: #3a3a42;
    font-size: 12px;
}

QLabel.ctxActive {
    color: #14b8a6;
    font-size: 12px;
    font-weight: 600;
}

QLabel.status {
    color: #55555e;
    font-size: 12px;
}

QLabel.status-error,
QLabel.statusError {
    color: #ef4444;
    font-size: 12px;
    font-weight: 600;
}

QLabel.status-success,
QLabel.statusOk {
    color: #22c55e;
    font-size: 12px;
    font-weight: 600;
}

QLabel.status-info,
QLabel.statusInfo {
    color: #14b8a6;
    font-size: 12px;
}

QLabel#validation {
    font-size: 11px;
    color: #3a3a42;
    padding-left: 2px;
}

QLabel#validation.validation-error {
    color: #ef4444;
}

QLabel#validation.validation-success {
    color: #22c55e;
}

QLabel#llmHealthBadge {
    border: 1px solid #26262b;
    border-radius: 10px;
    padding: 3px 10px;
    font-size: 11px;
    font-weight: 600;
    background: #17171a;
}

QLabel#version {
    font-size: 10px;
    color: #2a2a30;
    padding: 3px 8px;
    background: #141418;
    border-radius: 4px;
    border: 1px solid #1e1e24;
}

/* Cards */
QLabel.card-title {
    font-size: 11px;
    font-weight: 700;
    color: #14b8a6;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}

QLabel.card-title-large {
    font-size: 14px;
    font-weight: 700;
    color: #14b8a6;
}

QLabel#value {
    font-size: 18px;
    font-weight: 700;
    color: #ffffff;
}

QLabel.card-value {
    font-size: 13px;
    font-weight: 500;
    color: #c0c0c8;
}

QLabel.insights-text {
    color: #c0c0c8;
    font-size: 13px;
    line-height: 1.5;
}

QLabel#title {
    font-size: 22px;
    font-weight: 800;
    color: #14b8a6;
    letter-spacing: -0.5px;
}

QLabel#subtitle {
    font-size: 12px;
    color: #3a3a42;
}

QLabel.title {
    font-size: 16px;
    font-weight: 700;
    color: #14b8a6;
}

QLabel.subtitle {
    font-size: 14px;
    font-weight: 500;
    color: #e8e8ea;
}

QLabel.hint {
    color: #3a3a42;
    font-size: 11px;
    font-style: italic;
}

QLabel#ctxBadge {
    background: #0d1f1e;
    color: #14b8a6;
    border: 1px solid #1a3432;
    border-radius: 4px;
    padding: 4px 10px;
    font-size: 11px;
    font-weight: 600;
}

/* ═══════════════════════════════════════════════════════
   FRAMES / DIVIDERS / CARDS
═══════════════════════════════════════════════════════ */
QFrame.divider {
    background: #1e1e24;
    max-height: 1px;
    min-height: 1px;
    border: none;
    margin: 6px 0;
}

QFrame.card {
    background: #141418;
    border: 1px solid #1e1e24;
    border-radius: 8px;
}

QFrame#card {
    background: #141418;
    border: 1px solid #1e1e24;
    border-radius: 8px;
    min-width: 160px;
}

QFrame#chatTopBar {
    background: #0c0c0e;
    border-bottom: 1px solid #1c1c1f;
}

QFrame#topBarSep {
    background: #1c1c1f;
    max-width: 1px;
    min-width: 1px;
    border: none;
    margin: 8px 4px;
}

QFrame#chatInputArea {
    background: #0c0c0e;
    border-top: 1px solid #1c1c1f;
}

QFrame#chatDisplayWrapper {
    background: #0f0f11;
}

/* ═══════════════════════════════════════════════════════
   INNER TABS (QTabWidget inside panels)
═══════════════════════════════════════════════════════ */
QTabWidget::pane {
    border: 1px solid #1e1e24;
    border-radius: 6px;
    background: #111113;
    top: -1px;
}

QTabWidget::tab-bar {
    alignment: left;
}

QTabBar::tab {
    background: transparent;
    color: #3a3a42;
    padding: 7px 16px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 12px;
    font-weight: 500;
    margin-right: 2px;
}

QTabBar::tab:selected {
    color: #14b8a6;
    border-bottom: 2px solid #14b8a6;
    font-weight: 600;
}

QTabBar::tab:hover:!selected {
    color: #8888a0;
}

/* ═══════════════════════════════════════════════════════
   SCROLLBARS
═══════════════════════════════════════════════════════ */
QScrollBar:vertical {
    background: transparent;
    width: 6px;
    margin: 0;
    border: none;
}

QScrollBar::handle:vertical {
    background: #26262b;
    border-radius: 3px;
    min-height: 24px;
}

QScrollBar::handle:vertical:hover {
    background: #32323a;
}

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {
    height: 0;
    border: none;
}

QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical {
    background: transparent;
}

QScrollBar:horizontal {
    background: transparent;
    height: 6px;
    border: none;
}

QScrollBar::handle:horizontal {
    background: #26262b;
    border-radius: 3px;
    min-width: 24px;
}

QScrollBar::handle:horizontal:hover {
    background: #32323a;
}

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal {
    width: 0;
    border: none;
}

/* ═══════════════════════════════════════════════════════
   GROUP BOX
═══════════════════════════════════════════════════════ */
QGroupBox {
    border: 1px solid #1e1e24;
    border-radius: 8px;
    margin-top: 10px;
    padding-top: 14px;
    color: #e8e8ea;
    font-weight: 600;
    font-size: 12px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 6px;
    color: #4a4a52;
    font-size: 10px;
    font-weight: 700;
    letter-spacing: 1px;
    text-transform: uppercase;
}

/* ═══════════════════════════════════════════════════════
   CHECK BOX
═══════════════════════════════════════════════════════ */
QCheckBox {
    color: #c0c0c8;
    font-size: 13px;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid #32323a;
    background: #17171a;
}

QCheckBox::indicator:hover {
    border-color: #14b8a6;
}

QCheckBox::indicator:checked {
    background: #14b8a6;
    border-color: #14b8a6;
}

/* ═══════════════════════════════════════════════════════
   TOOLBAR (kept for compatibility, but hidden in new layout)
═══════════════════════════════════════════════════════ */
QToolBar#mainToolbar {
    background: #0c0c0e;
    border-bottom: 1px solid #1c1c1f;
    spacing: 4px;
    padding: 4px 10px;
}

QToolBar#mainToolbar QToolButton {
    background: #17171a;
    color: #6a6a72;
    border: 1px solid #26262b;
    border-radius: 5px;
    padding: 5px 10px;
    font-size: 12px;
}

QToolBar#mainToolbar QToolButton:hover {
    background: #1e1e22;
    color: #c0c0c8;
    border-color: #32323a;
}

/* ═══════════════════════════════════════════════════════
   SPLITTER
═══════════════════════════════════════════════════════ */
QSplitter::handle {
    background: #1e1e24;
}

QSplitter::handle:vertical {
    height: 1px;
}

QSplitter::handle:horizontal {
    width: 1px;
}

/* ═══════════════════════════════════════════════════════
   MULTI-SELECT MENU
═══════════════════════════════════════════════════════ */
QMenu#multi-select-menu {
    background: #1a1a1e;
    border: 1px solid #26262b;
    border-radius: 8px;
    padding: 4px;
}

QMenu#multi-select-menu QPushButton {
    background: transparent;
    color: #8888a0;
    border: none;
    border-radius: 5px;
    padding: 7px 12px;
    text-align: left;
    min-width: 160px;
    font-size: 12px;
}

QMenu#multi-select-menu QPushButton:hover {
    background: #222228;
    color: #c0c0c8;
}

QMenu#multi-select-menu QPushButton:checked {
    background: #0d1f1e;
    color: #14b8a6;
}
"""

LIGHT_THEME = """
QMainWindow {
    background-color: #ffffff;
    color: #1a1a1a;
}

QWidget { color: #1a1a1a; }
"""
