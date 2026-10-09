"""Compact desktop controls and readable document typography."""
import sys
from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap, QPalette
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

LIGHT = {
    "paper": "#ffffff", "sidebar": "#f6f6f8", "bar": "#ffffff",
    "text": "#25262a", "secondary": "#70727a", "border": "#e7e7eb",
    "hover": "#ececf0", "blue": "#007aff", "selected": "#ffffff",
    "code": "#f5f5f7",
}
DARK = {
    "paper": "#1c1c1e", "sidebar": "#18181b", "bar": "#1c1c1e",
    "text": "#f5f5f7", "secondary": "#a1a1a6", "border": "#343438",
    "hover": "#29292e", "blue": "#0a84ff", "selected": "#2c2c31",
    "code": "#2c2c2e",
}

PATHS = {
    "document": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M8 13h8M8 17h6"/>',
    "new": '<path d="M12 5v14M5 12h14"/>',
    "open": '<path d="M3 7V5a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v2M3 8h17l-3 12H3z"/>',
    "save": '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12l4 4v12a2 2 0 0 1-2 2zM7 3v6h10V3M7 21v-8h10v8"/>',
    "sidebar": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M9 3v18"/>',
    "outline": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "star": '<path d="m12 3 2.8 5.7 6.2.9-4.5 4.4 1.1 6.2-5.6-3-5.6 3 1.1-6.2L3 9.6l6.2-.9z"/>',
    "search": '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 5 5"/>',
    "more": '<circle cx="5" cy="12" r="1"/><circle cx="12" cy="12" r="1"/><circle cx="19" cy="12" r="1"/>',
    "bold": '<path d="M6 4h7a4 4 0 0 1 0 8H6zM6 12h8a4 4 0 0 1 0 8H6z"/>',
    "italic": '<path d="M19 4h-9M14 20H5M15 4 9 20"/>',
    "strike": '<path d="M17 5a6 6 0 0 0-10 3M7 17a6 6 0 0 0 10-2M3 12h18"/>',
    "code": '<path d="m8 6-6 6 6 6M16 6l6 6-6 6M14 3l-4 18"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
    "task": '<rect x="3" y="4" width="7" height="7" rx="1"/><path d="m4 7 2 2 4-4M14 7h7M14 17h7"/><rect x="3" y="14" width="7" height="7" rx="1"/>',
    "quote": '<path d="M4 5h6v7H4zM14 5h6v7h-6zM10 12c0 5-3 7-6 7M20 12c0 5-3 7-6 7"/>',
    "link": '<path d="m10 13 4-4M8 15l-2 2a4 4 0 0 1-5-5l4-4a4 4 0 0 1 5 0M16 9l2-2a4 4 0 0 1 5 5l-4 4a4 4 0 0 1-5 0" transform="translate(0 1)"/>',
    "table": '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M3 15h18M9 3v18M15 3v18"/>',
    "focus": '<path d="M8 3H3v5M16 3h5v5M3 16v5h5M21 16v5h-5"/>',
    "moon": '<path d="M20 14a8.5 8.5 0 0 1-10-10 8.5 8.5 0 1 0 10 10z"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5"/>',
    "chevron": '<path d="m9 5 7 7-7 7"/>',
    "close": '<path d="m6 6 12 12M6 18 18 6"/>',
}


FONT_SIZES = {"ui": 13, "body": 17, "code": 14}
HEADING_SIZES = {0: 17, 1: 32, 2: 24, 3: 21, 4: 19, 5: 18, 6: 17}
# Qt percentages scale the font metrics, rather than the CSS font size.
BODY_LINE_HEIGHT = 135
HEADING_LINE_HEIGHT = 120
CODE_LINE_HEIGHT = 135
PARAGRAPH_GAP = 6
HEADING_SPACING = {1: (20, 8), 2: (16, 6), 3: (12, 4), 4: (10, 4), 5: (10, 4), 6: (10, 4)}
CONTENT_WIDTH = 800
EDITOR_GUTTER = 56
EDITOR_TOP = 20
EDITOR_BOTTOM = 32

FONT_FAMILIES = {
    "win32": {
        "ui": ["Microsoft YaHei UI", "Microsoft YaHei", "Segoe UI"],
        "body": ["Microsoft YaHei", "Microsoft YaHei UI", "Segoe UI"],
        "code": ["Cascadia Code", "Cascadia Mono", "Consolas"],
    },
    "darwin": {
        "ui": ["SF Pro Text", "PingFang SC", "Helvetica Neue"],
        "body": ["SF Pro Text", "PingFang SC", "Helvetica Neue"],
        "code": ["SF Mono", "Menlo", "Monaco"],
    },
    "linux": {
        "ui": ["Inter", "Noto Sans", "Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC"],
        "body": ["Noto Sans CJK SC", "Noto Sans SC", "Source Han Sans SC", "Noto Sans", "DejaVu Sans"],
        "code": ["Noto Sans Mono CJK SC", "JetBrains Mono", "Noto Sans Mono", "DejaVu Sans Mono", "Liberation Mono"],
    },
}


def font_for(role):
    platform = sys.platform if sys.platform in FONT_FAMILIES else "linux"
    fixed = role == "code"
    system_role = QFontDatabase.SystemFont.FixedFont if fixed else QFontDatabase.SystemFont.GeneralFont
    font = QFontDatabase.systemFont(system_role)
    available = set(QFontDatabase.families())
    candidates = list(FONT_FAMILIES[platform][role])
    # macOS's native system family can be private and absent from the family list.
    if platform == "darwin" and not fixed:
        candidates.insert(0, font.family())
    candidates.append(font.family())
    if fixed:
        candidates.extend(FONT_FAMILIES[platform]["body"])
    families = []
    for family in candidates:
        if (family in available or family == font.family()) and family not in families:
            families.append(family)
    font.setFamilies(families)
    screen = QApplication.primaryScreen()
    logical_dpi = screen.logicalDotsPerInchY() if screen else 96
    # QTextEdit zoom and PDF printing require point sizes; keep logical sizes consistent.
    font.setPointSizeF(FONT_SIZES[role] * 72 / logical_dpi)
    font.setStyleHint(QFont.StyleHint.Monospace if fixed else QFont.StyleHint.SansSerif)
    font.setFixedPitch(fixed)
    return font


def application_font():
    return font_for("ui")


def icon(name, color="#6e6e73"):
    svg = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" '
           'stroke="' + color + '" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">' + PATHS[name] + '</svg>')
    pixmap = QPixmap(48, 48)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    QSvgRenderer(svg.encode()).render(painter)
    painter.end()
    pixmap.setDevicePixelRatio(2)
    return QIcon(pixmap)


def apply_theme(app, dark=False):
    colors = DARK if dark else LIGHT
    palette = QPalette()
    roles = {
        QPalette.ColorRole.Window: "sidebar", QPalette.ColorRole.WindowText: "text",
        QPalette.ColorRole.Base: "paper", QPalette.ColorRole.AlternateBase: "sidebar",
        QPalette.ColorRole.Text: "text", QPalette.ColorRole.Button: "bar",
        QPalette.ColorRole.ButtonText: "text", QPalette.ColorRole.Highlight: "blue",
        QPalette.ColorRole.HighlightedText: None, QPalette.ColorRole.ToolTipBase: "paper",
        QPalette.ColorRole.ToolTipText: "text", QPalette.ColorRole.PlaceholderText: "secondary",
    }
    for role, key in roles.items():
        palette.setColor(role, QColor(colors[key] if key else "#ffffff"))
    app.setPalette(palette)
    # Windows assigns menus a separate Segoe UI font, whose Chinese fallback can be SimSun.
    app.setFont(font_for("ui"), "QMenuBar")
    app.setFont(font_for("ui"), "QMenu")
    ui_families = ", ".join(f'"{family}"' for family in font_for("ui").families())
    body_families = ", ".join(f'"{family}"' for family in font_for("body").families())
    code_families = ", ".join(f'"{family}"' for family in font_for("code").families())
    body_points = font_for("body").pointSizeF()
    code_points = font_for("code").pointSizeF()
    app.setStyleSheet(f"""
        QWidget {{ color: {colors["text"]}; font-family: {ui_families}; font-size: {FONT_SIZES["ui"]}px; }}
        QMainWindow, QWidget#paper {{ background: {colors['paper']}; }}
        QFrame#sidebar {{ background: {colors['sidebar']}; border-right: 1px solid {colors['border']}; }}
        QFrame#header {{ background: {colors["paper"]}; border: none; }}
        QFrame#formatbar {{ background: {colors["paper"]}; border-bottom: 1px solid {colors["border"]}; }}
        QFrame#outline {{ background: {colors['paper']}; border-left: 1px solid {colors['border']}; }}
        QLabel#sectionLabel {{ color: {colors['secondary']}; font-size: 11px; font-weight: 600; }}
        QLabel#secondary, QLabel#fileLocation {{ color: {colors['secondary']}; font-size: 11px; }}
        QLabel#documentTitle {{ font-weight: 600; font-size: 14px; }}
        QLabel#brand {{ font-size: 19px; font-weight: 600; }}
        QToolButton {{ background: transparent; border: 1px solid transparent; border-radius: 5px; padding: 3px; }}
        QToolButton#typeButton {{ font-size: 16px; }}
        QToolButton::menu-indicator {{ image: none; width: 0; }}
        QToolButton:focus {{ border-color: {colors["blue"]}; }}
        QToolButton:hover {{ background: {colors['hover']}; }}
        QToolButton:checked {{ background: {colors["hover"]}; color: {colors["text"]}; }}
        QToolButton:disabled {{ color: {colors['secondary']}; }}
        QPushButton {{ background: transparent; border: 1px solid {colors["border"]}; border-radius: 5px; padding: 4px 10px; }}
        QPushButton:focus {{ border-color: {colors["blue"]}; }}
        QPushButton:hover {{ background: {colors['hover']}; }}
        QPushButton#saveButton {{ background: {colors["text"]}; border-color: {colors["text"]}; color: {colors["paper"]}; font-weight: 500; }}
        QPushButton#saveButton:hover {{ background: {colors["secondary"]}; border-color: {colors["secondary"]}; }}
        QPushButton#filterButton {{ border: 1px solid transparent; color: {colors["secondary"]}; padding: 4px 8px; }}
        QPushButton#filterButton:checked {{ background: {colors["selected"]}; border-color: {colors["border"]}; color: {colors["text"]}; }}
        QPushButton#filterButton:focus {{ border-color: {colors["blue"]}; }}
        QPushButton#openButton {{ text-align: left; border-color: {colors["border"]}; }}
        QLineEdit {{ background: {colors['paper']}; border: 1px solid {colors['border']}; border-radius: 5px; padding: 4px 8px; selection-background-color: {colors['blue']}; }}
        QLineEdit:focus {{ border: 1px solid {colors["blue"]}; }}
        QLineEdit#sidebarSearch {{ background: {colors["hover"]}; border: 1px solid transparent; border-radius: 8px; }}
        QLineEdit#sidebarSearch:focus {{ border-color: {colors["blue"]}; background: {colors["paper"]}; }}
        QComboBox {{ background: transparent; border: none; padding: 3px 7px; min-width: 62px; }}
        QComboBox:hover {{ background: {colors['hover']}; border-radius: 5px; }}
        QComboBox::drop-down {{ border: none; width: 18px; }}
        QListWidget {{ border: none; background: transparent; outline: none; }}
        QListWidget#outlineList::item {{ padding: 5px 6px; }}
        QListWidget#outlineList::item:selected {{ background: {colors['selected']}; color: {colors['blue']}; border-radius: 5px; }}
        QTextEdit, QPlainTextEdit {{ background: {colors['paper']}; border: none; selection-background-color: {colors['blue']}; selection-color: white; }}
        QTextEdit {{ font-family: {body_families}; font-size: {body_points}pt; }}
        QPlainTextEdit {{ font-family: {code_families}; font-size: {code_points}pt; }}
        QFrame#segments {{ background: {colors['hover']}; border-radius: 6px; }}
        QPushButton#segment {{ border: none; border-radius: 5px; padding: 3px 10px; color: {colors['secondary']}; }}
        QPushButton#segment:checked {{ background: {colors["paper"]}; color: {colors["text"]}; }}
        QPushButton#segment:focus {{ border: 1px solid {colors["blue"]}; }}
        QStatusBar {{ background: {colors["paper"]}; border-top: 1px solid {colors["border"]}; color: {colors['secondary']}; font-size: 11px; }}
        QStatusBar::item {{ border: none; }}
        QMenuBar {{ background: {colors["paper"]}; padding: 1px 6px; }}
        QMenuBar::item:selected, QMenu::item:selected {{ background: {colors['selected']}; color: {colors['text']}; }}
        QMenu {{ background: {colors['paper']}; padding: 5px; border: 1px solid {colors['border']}; }}
        QMenu::item {{ padding: 5px 20px; border-radius: 5px; }}
        QMenu::separator {{ height: 1px; background: {colors["border"]}; margin: 5px 10px; }}
        QScrollBar:vertical {{ background: transparent; width: 8px; margin: 4px 1px; }}
        QScrollBar::handle:vertical {{ background: {colors['border']}; border-radius: 3px; min-height: 30px; }}
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
        QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
        QFrame#blockPopup {{ background: {colors['paper']}; border: 1px solid {colors['border']}; border-radius: 8px; }}
        QFrame#blockPopup QLabel {{ border: none; background: transparent; font-size: 11px; }}
        QListWidget#blockItems::item {{ padding: 4px 8px; border-radius: 5px; }}
        QListWidget#blockItems::item:selected {{ background: {colors['hover']}; color: {colors['text']}; }}
        QToolButton#blockHandle {{ font-size: 20px; color: {colors['secondary']}; padding: 0; }}
        QFrame#blockDropLine {{ background: {colors['blue']}; }}
        QFrame#findbar {{ background: {colors['bar']}; border-bottom: 1px solid {colors['border']}; }}
    """)
    return colors
