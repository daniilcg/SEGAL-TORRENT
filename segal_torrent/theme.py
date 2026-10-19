from __future__ import annotations

from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

DARK = {
    "bg": "#1E1F22",
    "bg_elev": "#2B2D30",
    "bg_elev_2": "#313438",
    "bg_input": "#1E1F22",
    "hover": "#393B40",
    "pressed": "#43454A",
    "border": "#43454A",
    "border_soft": "#393B40",
    "text": "#DFE1E5",
    "text_dim": "#9DA0A8",
    "text_muted": "#6F737A",
    "accent": "#3574F0",
    "accent_hover": "#4B86F5",
    "accent_pressed": "#2A62D0",
    "selection": "#2E436E",
    "selection_text": "#FFFFFF",
    "green": "#499C54",
    "red": "#F75464",
    "yellow": "#D6B15A",
    "track": "#393B40",
    "scrollbar": "#4E5157",
    "scrollbar_hover": "#6B7078",
    "on_accent": "#FFFFFF",
}

LIGHT = {
    "bg": "#FFFFFF",
    "bg_elev": "#F7F8FA",
    "bg_elev_2": "#F0F1F3",
    "bg_input": "#FFFFFF",
    "hover": "#EBECF0",
    "pressed": "#DFE1E5",
    "border": "#D3D5DB",
    "border_soft": "#EBECF0",
    "text": "#19191C",
    "text_dim": "#6C707E",
    "text_muted": "#818594",
    "accent": "#3574F0",
    "accent_hover": "#2B62D4",
    "accent_pressed": "#2456C0",
    "selection": "#D4E2FF",
    "selection_text": "#19191C",
    "green": "#369650",
    "red": "#DB3B4B",
    "yellow": "#C27D00",
    "track": "#E4E6EB",
    "scrollbar": "#C4C6CC",
    "scrollbar_hover": "#A8ABB3",
    "on_accent": "#FFFFFF",
}


class Theme:
    def __init__(self, mode: str = "dark") -> None:
        self.mode = "light" if mode == "light" else "dark"

    @property
    def colors(self) -> dict[str, str]:
        return LIGHT if self.mode == "light" else DARK


def status_color(key: str, colors: dict[str, str]) -> str:
    if key in ("seeding", "finished"):
        return colors["green"]
    if key == "error":
        return colors["red"]
    if key in ("checking", "no_seeds"):
        return colors["yellow"]
    if key in ("paused", "queued"):
        return colors["text_dim"]
    return colors["text"]


def bar_color(key: str, colors: dict[str, str]) -> str:
    if key in ("seeding", "finished"):
        return colors["green"]
    if key == "error":
        return colors["red"]
    if key == "paused":
        return colors["text_muted"]
    if key == "queued":
        return colors["yellow"]
    return colors["accent"]


def stylesheet(colors: dict[str, str]) -> str:
    return """
    * {{
        font-family: "Segoe UI";
        font-size: 13px;
    }}
    QMainWindow, QDialog {{
        background: {bg};
        color: {text};
    }}
    QWidget {{
        color: {text};
    }}
    QMenuBar {{
        background: {bg_elev};
        color: {text};
        border: none;
        border-top: 2px solid {accent};
        border-bottom: 1px solid {border_soft};
        padding: 2px 6px;
    }}
    QMenuBar::item {{
        background: transparent;
        padding: 6px 10px;
        border-radius: 6px;
    }}
    QMenuBar::item:selected {{
        background: {hover};
    }}
    QMenu {{
        background: {bg_elev};
        color: {text};
        border: 1px solid {border};
        padding: 6px;
    }}
    QMenu::item {{
        padding: 6px 28px 6px 16px;
        border-radius: 6px;
    }}
    QMenu::item:selected {{
        background: {selection};
        color: {selection_text};
    }}
    QMenu::separator {{
        height: 1px;
        background: {border_soft};
        margin: 6px 8px;
    }}
    QToolBar {{
        background: {bg_elev};
        border: none;
        border-bottom: 1px solid {border_soft};
        spacing: 2px;
        padding: 6px 8px;
    }}
    QToolBar QToolButton {{
        background: transparent;
        color: {text};
        border: none;
        border-radius: 6px;
        padding: 4px;
        margin: 0 1px;
    }}
    QToolButton {{
        background: transparent;
        color: {text};
        border: none;
        border-radius: 6px;
        padding: 6px 10px;
    }}
    QToolButton:hover {{
        background: {hover};
    }}
    QToolButton:pressed, QToolButton:checked {{
        background: {pressed};
    }}
    QToolButton:disabled {{
        color: {text_muted};
    }}
    QLineEdit, QSpinBox, QComboBox {{
        background: {bg_input};
        color: {text};
        border: 1px solid {border};
        border-radius: 6px;
        padding: 6px 8px;
        selection-background-color: {accent};
        selection-color: {on_accent};
        min-height: 18px;
    }}
    QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
        border: 1px solid {accent};
    }}
    QComboBox::drop-down {{
        border: none;
        width: 22px;
    }}
    QComboBox QAbstractItemView {{
        background: {bg_elev};
        color: {text};
        border: 1px solid {border};
        selection-background-color: {selection};
        selection-color: {selection_text};
        outline: none;
    }}
    QSpinBox::up-button, QSpinBox::down-button {{
        width: 16px;
        border: none;
    }}
    QPushButton {{
        background: {bg_elev_2};
        color: {text};
        border: 1px solid {border};
        border-radius: 6px;
        padding: 6px 14px;
    }}
    QPushButton:hover {{
        background: {hover};
    }}
    QPushButton:pressed {{
        background: {pressed};
    }}
    QPushButton:disabled {{
        color: {text_muted};
    }}
    QPushButton#primary {{
        background: {accent};
        color: {on_accent};
        border: none;
    }}
    QPushButton#primary:hover {{
        background: {accent_hover};
    }}
    QPushButton#primary:pressed {{
        background: {accent_pressed};
    }}
    QPushButton#danger {{
        background: transparent;
        color: {red};
        border: 1px solid {red};
    }}
    QPushButton#danger:hover {{
        background: {hover};
    }}
    QTableView, QTableWidget, QTreeWidget {{
        background: {bg};
        color: {text};
        border: none;
        gridline-color: transparent;
        outline: none;
        selection-background-color: {selection};
        selection-color: {selection_text};
        alternate-background-color: {bg};
    }}
    QTableView::item, QTableWidget::item, QTreeWidget::item {{
        padding: 4px 8px;
        border: none;
        color: {text};
    }}
    QTableView::item:hover, QTableWidget::item:hover, QTreeWidget::item:hover {{
        background: {hover};
    }}
    QTableView::item:selected, QTableWidget::item:selected, QTreeWidget::item:selected {{
        background: {selection};
        color: {selection_text};
    }}
    QHeaderView::section {{
        background: {bg_elev};
        color: {text_dim};
        border: none;
        border-bottom: 1px solid {border_soft};
        padding: 8px 8px;
        font-weight: 600;
    }}
    QTreeWidget {{
        background: {bg};
    }}
    QTabWidget::pane {{
        border: none;
        border-top: 1px solid {border_soft};
        background: {bg};
        top: -1px;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {text_dim};
        padding: 8px 16px;
        border: none;
        border-bottom: 2px solid transparent;
    }}
    QTabBar::tab:selected {{
        color: {text};
        border-bottom: 2px solid {accent};
    }}
    QTabBar::tab:hover {{
        color: {text};
    }}
    QStatusBar {{
        background: {bg_elev};
        color: {text_dim};
        border-top: 1px solid {border_soft};
    }}
    QStatusBar::item {{
        border: none;
    }}
    QSplitter::handle {{
        background: {border_soft};
    }}
    QSplitter::handle:vertical {{
        height: 6px;
    }}
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:vertical {{
        background: {scrollbar};
        border-radius: 4px;
        min-height: 24px;
    }}
    QScrollBar::handle:vertical:hover {{
        background: {scrollbar_hover};
    }}
    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 2px;
    }}
    QScrollBar::handle:horizontal {{
        background: {scrollbar};
        border-radius: 4px;
        min-width: 24px;
    }}
    QScrollBar::add-line, QScrollBar::sub-line,
    QScrollBar::add-page, QScrollBar::sub-page {{
        background: transparent;
        height: 0;
        width: 0;
    }}
    QGroupBox {{
        color: {text};
        border: 1px solid {border};
        border-radius: 8px;
        margin-top: 14px;
        padding: 16px 12px 12px 12px;
        background: {bg};
    }}
    QGroupBox::title {{
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 12px;
        padding: 0 6px;
        color: {text_dim};
    }}
    QCheckBox {{
        spacing: 8px;
        color: {text};
    }}
    QLabel {{
        background: transparent;
        color: {text};
    }}
    QLabel#dim, QLabel#subtle {{
        color: {text_dim};
    }}
    QLabel#title {{
        font-size: 20px;
        font-weight: 600;
        color: {text};
    }}
    QLabel#emptyTitle {{
        font-size: 18px;
        font-weight: 600;
    }}
    QToolTip {{
        background: {bg_elev};
        color: {text};
        border: 1px solid {border};
        padding: 4px 8px;
    }}
    QScrollArea, QAbstractScrollArea {{
        border: none;
        background: {bg};
    }}
    QScrollArea > QWidget > QWidget {{
        background: {bg};
    }}
    """.format(**colors)


def apply_theme(app: QApplication, theme: Theme) -> None:
    colors = theme.colors
    app.setStyleSheet(stylesheet(colors))
    palette = QPalette()
    palette.setColor(QPalette.ColorRole.Window, QColor(colors["bg"]))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Base, QColor(colors["bg_input"]))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(colors["bg_elev"]))
    palette.setColor(QPalette.ColorRole.Text, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Button, QColor(colors["bg_elev"]))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(colors["text"]))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(colors["accent"]))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(colors["on_accent"]))
    palette.setColor(QPalette.ColorRole.Link, QColor(colors["accent"]))
    palette.setColor(QPalette.ColorRole.PlaceholderText, QColor(colors["text_muted"]))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(colors["bg_elev"]))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(colors["text"]))
    app.setPalette(palette)
