from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import QByteArray, QSize, QSortFilterProxyModel, Qt, QTimer
from PySide6.QtGui import QAction, QBrush, QCloseEvent, QColor, QDragEnterEvent, QDropEvent, QIcon, QKeySequence, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QToolBar,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from segal_torrent.dialogs import (
    AboutDialog,
    AddTorrentDialog,
    MagnetDialog,
    PeerDialog,
    SettingsDialog,
    confirm_remove,
)
from segal_torrent.engine import Engine, TorrentDetails
from segal_torrent.formatutil import format_percent, format_size, format_speed, torrent_count
from segal_torrent.i18n import I18n
from segal_torrent.icons import toolbar_icon
from segal_torrent.paths import asset
from segal_torrent.settings_store import Settings
from segal_torrent.table import ProgressDelegate, TorrentModel
from segal_torrent.theme import Theme, apply_theme


class TorrentFilter(QSortFilterProxyModel):
    def __init__(self) -> None:
        super().__init__()
        self._query = ""
        self.setFilterCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
        self.setSortRole(Qt.ItemDataRole.UserRole)

    def set_query(self, text: str) -> None:
        self._query = text.strip().casefold()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        if not self._query:
            return True
        index = self.sourceModel().index(source_row, 0, source_parent)
        name = self.sourceModel().data(index, Qt.ItemDataRole.DisplayRole) or ""
        return self._query in str(name).casefold()


class MainWindow(QMainWindow):
    def __init__(self, settings: Settings | None = None) -> None:
        super().__init__()
        self.settings = settings or Settings()
        lang = self.settings.language if self.settings.language in ("en", "ru") else "en"
        self.i18n = I18n(lang)
        self.theme = Theme(self.settings.theme)
        self.engine = Engine(self.settings)
        self.engine.start()
        self._flash_until = 0.0
        self._flash_text = ""
        self._files_sig = None
        self._file_items: dict[int, QTreeWidgetItem] = {}
        self._files_block = False
        self._details_sized = False
        self.settings.details_visible = True
        self.setWindowTitle("SEGAL-TORRENT")
        icon_path = asset("icon.png")
        if icon_path.is_file():
            self.setWindowIcon(QIcon(str(icon_path)))
        self.resize(1120, 740)
        self.setMinimumSize(880, 560)
        self.setAcceptDrops(True)
        self._build()
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self.theme)
        self._apply_icons()
        self.retranslate()
        if self.settings.geometry:
            try:
                self.restoreGeometry(QByteArray.fromBase64(self.settings.geometry.encode("ascii")))
            except Exception:
                pass
        self.details.setMinimumHeight(180)
        self._apply_details_pane(self.settings.details_visible and self.model.rowCount() > 0)
        self.timer = QTimer(self)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self.refresh)
        self.timer.start()
        self.refresh()

    def _build(self) -> None:
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self.model = TorrentModel(self.i18n, self.theme)
        self.proxy = TorrentFilter()
        self.proxy.setSourceModel(self.model)
        self.table = self._build_table()
        self.empty = self._build_empty()
        self.stack = QStackedWidget()
        self.stack.addWidget(self.empty)
        self.stack.addWidget(self.table)
        self.details = self._build_details()
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.addWidget(self.stack)
        self.splitter.addWidget(self.details)
        self.splitter.setStretchFactor(0, 3)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setChildrenCollapsible(False)
        central = QWidget()
        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.splitter)
        self.setCentralWidget(central)
        status = QStatusBar()
        self.status_label = QLabel()
        status.addWidget(self.status_label, 1)
        self.setStatusBar(status)

    def _build_actions(self) -> None:
        self.act_add = QAction(self)
        self.act_add.setShortcut(QKeySequence.StandardKey.Open)
        self.act_add.triggered.connect(lambda: self.add_torrent())
        self.act_magnet = QAction(self)
        self.act_magnet.setShortcut(QKeySequence("Ctrl+M"))
        self.act_magnet.triggered.connect(lambda: self.add_magnet())
        self.act_settings = QAction(self)
        self.act_settings.setShortcut(QKeySequence("Ctrl+,"))
        self.act_settings.triggered.connect(self.open_settings)
        self.act_exit = QAction(self)
        self.act_exit.setShortcut(QKeySequence.StandardKey.Quit)
        self.act_exit.triggered.connect(self.close)
        self.act_pause = QAction(self)
        self.act_pause.triggered.connect(lambda: self.pause_selected())
        self.act_resume = QAction(self)
        self.act_resume.triggered.connect(lambda: self.resume_selected())
        self.act_remove = QAction(self)
        self.act_remove.triggered.connect(lambda: self.remove_selected(False))
        self.act_remove_files = QAction(self)
        self.act_remove_files.triggered.connect(lambda: self.remove_selected(True))
        self.act_folder = QAction(self)
        self.act_folder.triggered.connect(self.open_selected_folder)
        self.act_magnet_copy = QAction(self)
        self.act_magnet_copy.triggered.connect(self.copy_magnet)
        self.act_hash = QAction(self)
        self.act_hash.triggered.connect(self.copy_hash)
        self.act_recheck = QAction(self)
        self.act_recheck.triggered.connect(self.recheck_selected)
        self.act_reannounce = QAction(self)
        self.act_reannounce.triggered.connect(self.reannounce_selected)
        self.act_seq = QAction(self)
        self.act_seq.setCheckable(True)
        self.act_seq.toggled.connect(self._toggle_sequential)
        self.act_peer = QAction(self)
        self.act_peer.triggered.connect(self.connect_peer)
        self.act_theme = QAction(self)
        self.act_theme.triggered.connect(self.toggle_theme)
        self.act_details = QAction(self)
        self.act_details.setCheckable(True)
        self.act_details.setChecked(self.settings.details_visible)
        self.act_details.toggled.connect(self._toggle_details)
        self.act_en = QAction(self)
        self.act_en.setCheckable(True)
        self.act_en.triggered.connect(lambda: self.set_language("en"))
        self.act_ru = QAction(self)
        self.act_ru.setCheckable(True)
        self.act_ru.triggered.connect(lambda: self.set_language("ru"))
        self.act_about = QAction(self)
        self.act_about.triggered.connect(self.open_about)
        self.act_data = QAction(self)
        self.act_data.triggered.connect(self.open_data_folder)

    def _build_menus(self) -> None:
        file_menu = self.menuBar().addMenu("")
        file_menu.addAction(self.act_add)
        file_menu.addAction(self.act_magnet)
        file_menu.addSeparator()
        file_menu.addAction(self.act_settings)
        file_menu.addSeparator()
        file_menu.addAction(self.act_exit)
        torrent_menu = self.menuBar().addMenu("")
        torrent_menu.addAction(self.act_pause)
        torrent_menu.addAction(self.act_resume)
        torrent_menu.addAction(self.act_seq)
        torrent_menu.addSeparator()
        torrent_menu.addAction(self.act_recheck)
        torrent_menu.addAction(self.act_reannounce)
        torrent_menu.addAction(self.act_peer)
        torrent_menu.addSeparator()
        torrent_menu.addAction(self.act_folder)
        torrent_menu.addAction(self.act_magnet_copy)
        torrent_menu.addAction(self.act_hash)
        torrent_menu.addSeparator()
        torrent_menu.addAction(self.act_remove)
        torrent_menu.addAction(self.act_remove_files)
        view_menu = self.menuBar().addMenu("")
        view_menu.addAction(self.act_theme)
        view_menu.addAction(self.act_details)
        view_menu.addSeparator()
        lang_menu = view_menu.addMenu("")
        lang_menu.addAction(self.act_en)
        lang_menu.addAction(self.act_ru)
        help_menu = self.menuBar().addMenu("")
        help_menu.addAction(self.act_data)
        help_menu.addAction(self.act_about)
        self._menus = (file_menu, torrent_menu, view_menu, lang_menu, help_menu)

    def _build_toolbar(self) -> None:
        bar = QToolBar()
        bar.setMovable(False)
        bar.setFloatable(False)
        bar.setIconSize(QSize(18, 18))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.tool_buttons: list[tuple[QToolButton, QAction, str]] = []
        for action, key in (
            (self.act_add, "tool_add"),
            (self.act_magnet, "tool_magnet"),
        ):
            bar.addWidget(self._make_tool_button(action, key))
        bar.addSeparator()
        for action, key in (
            (self.act_pause, "tool_pause"),
            (self.act_resume, "tool_resume"),
            (self.act_remove, "tool_remove"),
        ):
            bar.addWidget(self._make_tool_button(action, key))
        bar.addSeparator()
        bar.addWidget(self._make_tool_button(self.act_folder, "tool_folder"))
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setFixedWidth(220)
        self.search.textChanged.connect(self.proxy_query)
        bar.addWidget(self.search)
        self.lang_button = QToolButton()
        self.lang_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.lang_button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.lang_menu = QMenu(self)
        self.lang_menu.addAction(self.act_en)
        self.lang_menu.addAction(self.act_ru)
        self.lang_button.setMenu(self.lang_menu)
        bar.addWidget(self.lang_button)
        bar.addWidget(self._make_tool_button(self.act_theme, "tool_theme"))
        self.addToolBar(bar)
        self.toolbar = bar

    def _make_tool_button(self, action: QAction, key: str) -> QToolButton:
        button = QToolButton()
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setAutoRaise(True)
        button.setFixedSize(34, 34)
        button.clicked.connect(action.trigger)
        self.tool_buttons.append((button, action, key))
        return button

    def _sync_tools(self) -> None:
        for button, action, key in self.tool_buttons:
            button.setIcon(action.icon())
            button.setEnabled(action.isEnabled())
            button.setToolTip(action.text())
            button.setText(action.text())

    def _build_table(self):
        view = QTableView()
        view.setModel(self.proxy)
        view.setItemDelegateForColumn(2, ProgressDelegate(self.theme, view))
        view.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        view.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        view.setShowGrid(False)
        view.setWordWrap(False)
        view.setAlternatingRowColors(False)
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.verticalHeader().setVisible(False)
        view.verticalHeader().setDefaultSectionSize(40)
        view.setTextElideMode(Qt.TextElideMode.ElideRight)
        view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        view.setSortingEnabled(True)
        view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        view.customContextMenuRequested.connect(self._context_menu)
        view.doubleClicked.connect(lambda _index: self.open_selected_folder())
        view.selectionModel().selectionChanged.connect(lambda *_: self._sync_details())
        header = view.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for column, width in ((1, 96), (2, 180), (3, 130), (4, 110), (5, 110), (6, 110), (7, 72), (8, 72)):
            header.setSectionResizeMode(column, QHeaderView.ResizeMode.Interactive)
            view.setColumnWidth(column, width)
        header.setMinimumSectionSize(56)
        self.view = view
        return view

    def _build_empty(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.addStretch(2)
        self.empty_icon = QLabel()
        self.empty_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_path = asset("icon.png")
        if icon_path.is_file():
            pix = QPixmap(str(icon_path))
            self.empty_icon.setPixmap(pix.scaled(84, 84, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.empty_title = QLabel()
        self.empty_title.setObjectName("emptyTitle")
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_body = QLabel()
        self.empty_body.setObjectName("dim")
        self.empty_body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_button = QPushButton()
        self.empty_button.setObjectName("primary")
        self.empty_button.clicked.connect(lambda: self.add_torrent())
        layout.addWidget(self.empty_icon)
        layout.addWidget(self.empty_title)
        layout.addWidget(self.empty_body)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.empty_button)
        row.addStretch(1)
        layout.addSpacing(8)
        layout.addLayout(row)
        layout.addStretch(3)
        return widget

    def _build_details(self) -> QTabWidget:
        tabs = QTabWidget()
        tabs.setDocumentMode(True)
        tabs.setMinimumHeight(180)
        general = QWidget()
        grid = QGridLayout(general)
        grid.setContentsMargins(16, 14, 16, 14)
        grid.setHorizontalSpacing(28)
        grid.setVerticalSpacing(10)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        grid.setColumnMinimumWidth(0, 148)
        grid.setColumnMinimumWidth(2, 148)
        self.general_values: dict[str, QLabel] = {}
        self.general_names: dict[str, QLabel] = {}
        # (key, row, column). A value spanning both columns uses column 0.
        places = (
            ("name", 0, 0, 3),
            ("status", 1, 0, 1),
            ("size", 1, 2, 1),
            ("progress", 2, 0, 1),
            ("selected", 2, 2, 1),
            ("pieces", 3, 0, 1),
            ("piece_size", 3, 2, 1),
            ("downloaded", 4, 0, 1),
            ("uploaded", 4, 2, 1),
            ("ratio", 5, 0, 1),
            ("availability", 5, 2, 1),
            ("creator", 6, 0, 1),
            ("error", 6, 2, 1),
            ("info_hash", 7, 0, 3),
            ("info_hash_v2", 8, 0, 3),
            ("path", 9, 0, 3),
            ("comment", 10, 0, 3),
        )
        for key, row, column, span in places:
            name = QLabel()
            name.setObjectName("dim")
            name.setFixedHeight(22)
            name.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            value = QLabel("—")
            value.setFixedHeight(22)
            value.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
            grid.addWidget(name, row, column)
            grid.addWidget(value, row, column + 1, 1, span)
            self.general_names[key] = name
            self.general_values[key] = value
        grid.setRowStretch(11, 1)
        self.general_page = general
        self.general_grid = grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(general)
        self.files_tree = QTreeWidget()
        self.files_tree.setColumnCount(3)
        self.files_tree.setRootIsDecorated(True)
        self.files_tree.setTextElideMode(Qt.TextElideMode.ElideRight)
        file_header = self.files_tree.header()
        file_header.setStretchLastSection(False)
        file_header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        file_header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        file_header.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.files_tree.itemChanged.connect(self._on_file_changed)
        self.files_placeholder = QLabel()
        self.files_placeholder.setObjectName("dim")
        self.files_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        files_page = QWidget()
        files_layout = QVBoxLayout(files_page)
        files_layout.setContentsMargins(0, 0, 0, 0)
        files_layout.addWidget(self.files_placeholder)
        files_layout.addWidget(self.files_tree)
        self.trackers_table = self._detail_table()
        self.peers_table = self._detail_table()
        tabs.addTab(scroll, "")
        tabs.addTab(files_page, "")
        tabs.addTab(self.trackers_table, "")
        tabs.addTab(self.peers_table, "")
        self.detail_tabs = tabs
        return tabs

    def _detail_table(self) -> QTableWidget:
        table = QTableWidget(0, 1)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setShowGrid(False)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setStretchLastSection(True)
        table.setFrameShape(QFrame.Shape.NoFrame)
        return table

    def retranslate(self) -> None:
        self.act_add.setText(self.i18n.t("add_torrent"))
        self.act_magnet.setText(self.i18n.t("add_magnet"))
        self.act_settings.setText(self.i18n.t("settings"))
        self.act_exit.setText(self.i18n.t("exit"))
        self.act_pause.setText(self.i18n.t("pause"))
        self.act_resume.setText(self.i18n.t("resume"))
        self.act_remove.setText(self.i18n.t("remove"))
        self.act_remove_files.setText(self.i18n.t("remove_files"))
        self.act_folder.setText(self.i18n.t("open_folder"))
        self.act_magnet_copy.setText(self.i18n.t("copy_magnet"))
        self.act_hash.setText(self.i18n.t("copy_hash"))
        self.act_recheck.setText(self.i18n.t("recheck"))
        self.act_reannounce.setText(self.i18n.t("reannounce"))
        self.act_seq.setText(self.i18n.t("sequential"))
        self.act_peer.setText(self.i18n.t("connect_peer"))
        self.act_about.setText(self.i18n.t("about"))
        self.act_data.setText(self.i18n.t("open_data"))
        self.act_en.setText(self.i18n.t("english"))
        self.act_ru.setText(self.i18n.t("russian"))
        self.act_en.blockSignals(True)
        self.act_ru.blockSignals(True)
        self.act_en.setChecked(self.i18n.lang == "en")
        self.act_ru.setChecked(self.i18n.lang == "ru")
        self.act_en.blockSignals(False)
        self.act_ru.blockSignals(False)
        dark = self.theme.mode == "dark"
        self.act_theme.setText(self.i18n.t("light_theme" if dark else "dark_theme"))
        self.act_theme.setToolTip(self.i18n.t("switch_light" if dark else "switch_dark"))
        self.act_details.setText(self.i18n.t("hide_details" if self.details.isVisible() else "show_details"))
        names = ("file_menu", "torrent_menu", "view_menu", "language", "help_menu")
        for menu, key in zip(self._menus, names):
            menu.setTitle(self.i18n.t(key))
        self.search.setPlaceholderText(self.i18n.t("search"))
        self.lang_button.setText("RU" if self.i18n.lang == "ru" else "EN")
        self.lang_button.setToolTip(self.i18n.t("language"))
        self.empty_title.setText(self.i18n.t("empty_title"))
        self.empty_body.setText(self.i18n.t("empty_body"))
        self.empty_button.setText(self.i18n.t("empty_button"))
        self.files_placeholder.setText(self.i18n.t("metadata_wait"))
        self.files_tree.setHeaderLabels([self.i18n.t("file_col"), self.i18n.t("size"), self.i18n.t("progress")])
        self.detail_tabs.setTabText(0, self.i18n.t("general"))
        self.detail_tabs.setTabText(1, self.i18n.t("files"))
        self.detail_tabs.setTabText(2, self.i18n.t("trackers"))
        self.detail_tabs.setTabText(3, self.i18n.t("peers_tab"))
        labels = {
            "name": "name",
            "status": "status",
            "error": "error",
            "info_hash": "info_hash",
            "info_hash_v2": "info_hash_v2",
            "size": "size",
            "selected": "selected",
            "progress": "progress",
            "pieces": "pieces",
            "piece_size": "piece_size",
            "path": "path",
            "downloaded": "downloaded",
            "uploaded": "uploaded",
            "ratio": "ratio",
            "availability": "availability",
            "creator": "creator",
            "comment": "comment",
        }
        for key, text_key in labels.items():
            if key == "selected":
                self.general_names[key].setText(self.i18n.t("selected_label"))
            else:
                self.general_names[key].setText(self.i18n.t(text_key))
        self.model.retranslate()
        self._files_sig = None
        self._apply_icons()
        self._sync_tools()
        self._sync_details()

    def _apply_icons(self) -> None:
        color = self.theme.colors["text"]
        self.act_add.setIcon(toolbar_icon("plus", color))
        self.act_magnet.setIcon(toolbar_icon("magnet", color))
        self.act_pause.setIcon(toolbar_icon("pause", color))
        self.act_resume.setIcon(toolbar_icon("play", color))
        self.act_remove.setIcon(toolbar_icon("trash", color))
        self.act_folder.setIcon(toolbar_icon("folder", color))
        self.act_theme.setIcon(toolbar_icon("sun" if self.theme.mode == "dark" else "moon", color))
        self._sync_tools()

    def offer_default_app(self) -> None:
        from segal_torrent.associations import is_torrent_default, open_default_ui, register

        try:
            register()
        except Exception:
            return
        if self.settings.asked_default or is_torrent_default():
            return
        box = QMessageBox(self)
        box.setWindowTitle(self.i18n.t("default_app_title"))
        box.setText(self.i18n.t("default_app_prompt"))
        box.setIcon(QMessageBox.Icon.Question)
        yes = box.addButton(self.i18n.t("default_app_yes"), QMessageBox.ButtonRole.YesRole)
        box.addButton(self.i18n.t("default_app_no"), QMessageBox.ButtonRole.NoRole)
        box.exec()
        self.settings.asked_default = True
        self.settings.save()
        if box.clickedButton() is yes:
            open_default_ui()

    def set_language(self, lang: str) -> None:
        self.i18n.set_language(lang)
        self.settings.language = self.i18n.lang
        self.settings.save()
        self.retranslate()

    def set_theme(self, mode: str) -> None:
        self.theme.mode = "light" if mode == "light" else "dark"
        self.settings.theme = self.theme.mode
        self.settings.save()
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, self.theme)
        self._apply_icons()
        self.retranslate()
        self.view.viewport().update()

    def toggle_theme(self) -> None:
        self.set_theme("light" if self.theme.mode == "dark" else "dark")

    def proxy_query(self, text: str) -> None:
        self.proxy.set_query(text)
        self._update_empty()

    def refresh(self) -> None:
        self.engine.pump()
        for code, extra in self.engine.pop_notices():
            QMessageBox.warning(self, self.i18n.t("error_title"), self.i18n.t(code, name=extra))
        self.model.sync(self.engine.rows())
        self._ensure_selection()
        self._update_empty()
        self._update_actions()
        self._sync_details()
        self._update_status()

    def _ensure_selection(self) -> None:
        if self.model.rowCount() == 0:
            return
        selection = self.view.selectionModel()
        if selection is None or selection.hasSelection():
            return
        index = self.proxy.index(0, 0)
        if not index.isValid():
            return
        self.view.setCurrentIndex(index)
        selection.select(
            index,
            selection.SelectionFlag.ClearAndSelect | selection.SelectionFlag.Rows,
        )

    def _update_empty(self) -> None:
        has_rows = self.model.rowCount() > 0
        self.stack.setCurrentIndex(1 if has_rows else 0)
        self._apply_details_pane(has_rows and self.act_details.isChecked())

    def _apply_details_pane(self, visible: bool) -> None:
        opening = visible and not self.details.isVisible()
        self.details.setVisible(visible)
        if not visible:
            return
        sizes = self.splitter.sizes()
        too_small = len(sizes) != 2 or sizes[1] < 160
        if not (opening or too_small):
            return
        self._details_sized = True
        total = max(sum(sizes), self.height() or 740)
        bottom = min(360, max(260, int(total * 0.4)))
        self.splitter.setSizes([max(220, total - bottom), bottom])

    def _update_status(self) -> None:
        if time.time() < self._flash_until:
            self.status_label.setText(self._flash_text)
            return
        stats = self.engine.stats()
        listen = self.i18n.t("listening", port=stats.port) if stats.listening else self.i18n.t("offline")
        text = "    ".join(
            (
                self.i18n.t("dht", count=stats.dht_nodes),
                "↓ " + format_speed(stats.down_rate, self.i18n.lang),
                "↑ " + format_speed(stats.up_rate, self.i18n.lang),
                torrent_count(self.model.rowCount(), self.i18n.lang),
                listen,
            )
        )
        self.status_label.setText(text)

    def _flash(self, text: str) -> None:
        self._flash_text = text
        self._flash_until = time.time() + 2.5
        self.status_label.setText(text)

    def _update_actions(self) -> None:
        ids = self.selected_ids()
        rows = [self.model.row_by_id(tid) for tid in ids]
        rows = [row for row in rows if row is not None]
        self.act_pause.setEnabled(any(not row.paused for row in rows))
        self.act_resume.setEnabled(any(row.paused for row in rows))
        self.act_remove.setEnabled(bool(rows))
        self.act_remove_files.setEnabled(bool(rows))
        single = len(rows) == 1
        self.act_folder.setEnabled(single)
        self.act_magnet_copy.setEnabled(single)
        self.act_hash.setEnabled(single)
        self.act_recheck.setEnabled(single)
        self.act_reannounce.setEnabled(single)
        self.act_peer.setEnabled(single)
        self.act_seq.setEnabled(bool(rows))
        self.act_seq.blockSignals(True)
        self.act_seq.setChecked(bool(rows) and all(row.sequential for row in rows))
        self.act_seq.blockSignals(False)
        self._sync_tools()

    def selected_ids(self) -> list[str]:
        selection = self.view.selectionModel()
        if selection is None:
            return []
        ids: list[str] = []
        for index in selection.selectedRows():
            source = self.proxy.mapToSource(index)
            row = source.row()
            if 0 <= row < len(self.model.rows):
                ids.append(self.model.rows[row].id)
        return ids

    def current_id(self) -> str | None:
        index = self.view.currentIndex()
        if index.isValid():
            source = self.proxy.mapToSource(index)
            row = source.row()
            if 0 <= row < len(self.model.rows):
                return self.model.rows[row].id
        ids = self.selected_ids()
        return ids[0] if ids else None

    def add_torrent(self, path: str | None = None) -> None:
        if not path:
            chosen, _filter = QFileDialog.getOpenFileName(
                self,
                self.i18n.t("add_torrent"),
                self.settings.download_dir,
                self.i18n.t("torrent_filter"),
            )
            if not chosen:
                return
            path = chosen
        preview, err = self.engine.preview(path)
        if preview is None:
            QMessageBox.warning(self, self.i18n.t("error_title"), self.i18n.t(err or "invalid_torrent"))
            return
        dialog = AddTorrentDialog(
            preview,
            self.settings.download_dir,
            self.settings.start_immediately,
            self.i18n,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        if values is None:
            return
        save_path, selected, start, sequential = values
        self._remember_download_dir(save_path)
        ok, code, _tid = self.engine.add_file(path, save_path, selected, start, sequential)
        if not ok:
            QMessageBox.warning(self, self.i18n.t("error_title"), self.i18n.t(code or "add_failed"))
        self.refresh()

    def add_magnet(self, magnet: str = "") -> None:
        dialog = MagnetDialog(
            self.settings.download_dir,
            self.settings.start_immediately,
            self.i18n,
            magnet,
            self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        uri, save_path, start = dialog.values()
        self._remember_download_dir(save_path)
        ok, code, _tid = self.engine.add_magnet(uri, save_path, start)
        if not ok:
            QMessageBox.warning(self, self.i18n.t("error_title"), self.i18n.t(code or "invalid_magnet"))
        self.refresh()

    def open_inputs(self, items: list[str]) -> None:
        self.showNormal()
        self.raise_()
        self.activateWindow()
        for item in items:
            text = item.strip().strip('"')
            if not text:
                continue
            if text.startswith("magnet:?"):
                self.add_magnet(text)
            elif text.lower().endswith(".torrent") and os.path.isfile(text):
                self.add_torrent(text)

    def pause_selected(self) -> None:
        self.engine.pause(self.selected_ids())
        self.refresh()

    def resume_selected(self) -> None:
        self.engine.resume(self.selected_ids())
        self.refresh()

    def remove_selected(self, delete_files: bool) -> None:
        ids = self.selected_ids()
        if not ids:
            return
        names = []
        for tid in ids:
            row = self.model.row_by_id(tid)
            names.append(row.name if row else tid)
        if not confirm_remove(self, self.i18n, names, delete_files):
            return
        self.engine.remove(ids, delete_files)
        self.refresh()

    def open_selected_folder(self) -> None:
        tid = self.current_id()
        if not tid:
            return
        path = self.engine.location(tid)
        if path is None:
            return
        self._reveal(Path(path))

    def copy_magnet(self) -> None:
        tid = self.current_id()
        if not tid:
            return
        uri = self.engine.magnet_uri(tid)
        if not uri:
            return
        QApplication.clipboard().setText(uri)
        self._flash(self.i18n.t("copied"))

    def copy_hash(self) -> None:
        tid = self.current_id()
        if not tid:
            return
        QApplication.clipboard().setText(self.engine.info_hash(tid))
        self._flash(self.i18n.t("copied"))

    def recheck_selected(self) -> None:
        tid = self.current_id()
        if tid:
            self.engine.force_recheck(tid)

    def reannounce_selected(self) -> None:
        tid = self.current_id()
        if tid:
            self.engine.force_reannounce(tid)

    def _toggle_sequential(self, checked: bool) -> None:
        for tid in self.selected_ids():
            self.engine.set_sequential(tid, checked)
        self.refresh()

    def connect_peer(self) -> None:
        tid = self.current_id()
        if not tid:
            return
        dialog = PeerDialog(self.i18n, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        endpoint = dialog.endpoint()
        if endpoint is None:
            return
        host, port = endpoint
        self.engine.connect_peer(tid, host, port)

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.settings, self.i18n, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        values = dialog.values()
        folder = values["download_dir"]
        try:
            Path(folder).mkdir(parents=True, exist_ok=True)
        except OSError:
            QMessageBox.warning(self, self.i18n.t("error_title"), self.i18n.t("folder_missing"))
            return
        self.settings.download_dir = folder
        self.settings.listen_port = int(values["listen_port"])
        self.settings.max_download_kb = int(values["max_download_kb"])
        self.settings.max_upload_kb = int(values["max_upload_kb"])
        self.settings.active_downloads = int(values["active_downloads"])
        self.settings.start_immediately = bool(values["start_immediately"])
        self.settings.save()
        self.engine.apply_runtime()
        if values["language"] != self.i18n.lang:
            self.set_language(values["language"])
        if values["theme"] != self.theme.mode:
            self.set_theme(values["theme"])
        else:
            self.retranslate()

    def open_about(self) -> None:
        AboutDialog(self.i18n, self).exec()

    def open_data_folder(self) -> None:
        os.startfile(self.settings.folder)

    def _remember_download_dir(self, folder: str) -> None:
        folder = folder.strip()
        if not folder:
            return
        self.settings.download_dir = folder
        self.settings.save()

    def _toggle_details(self, visible: bool) -> None:
        self.settings.details_visible = visible
        self.settings.save()
        self._update_empty()
        self.act_details.setText(self.i18n.t("hide_details" if visible else "show_details"))

    def _context_menu(self, pos) -> None:
        menu = QMenu(self)
        menu.addAction(self.act_pause)
        menu.addAction(self.act_resume)
        menu.addAction(self.act_seq)
        menu.addSeparator()
        menu.addAction(self.act_folder)
        menu.addAction(self.act_magnet_copy)
        menu.addAction(self.act_hash)
        menu.addAction(self.act_recheck)
        menu.addAction(self.act_reannounce)
        menu.addAction(self.act_peer)
        menu.addSeparator()
        menu.addAction(self.act_remove)
        menu.addAction(self.act_remove_files)
        menu.exec(self.view.viewport().mapToGlobal(pos))

    def _sync_details(self) -> None:
        tid = self.current_id()
        if not tid:
            self._clear_details()
            return
        detail = self.engine.details(tid)
        if detail is None:
            self._clear_details()
            return
        self._fill_general(detail)
        self._sync_files(detail)
        self._fill_trackers(detail)
        self._fill_peers(detail)

    def _clear_details(self) -> None:
        for key in self.general_values:
            self._show_general_value(key, "—")
        self._fit_general()
        self.files_tree.clear()
        self._file_items.clear()
        self._files_sig = None
        self.files_placeholder.setVisible(True)
        self.files_tree.setVisible(False)
        self.trackers_table.setRowCount(0)
        self.peers_table.setRowCount(0)

    def _fill_general(self, detail: TorrentDetails) -> None:
        lang = self.i18n.lang
        values = {
            "name": detail.name,
            "status": self.i18n.t(f"status_{detail.status_key}"),
            "error": detail.error or "—",
            "info_hash": detail.info_hash,
            "info_hash_v2": detail.info_hash_v2 or "—",
            "size": format_size(detail.size, lang) if detail.size else "—",
            "selected": format_size(detail.selected, lang) if detail.selected else "—",
            "progress": format_percent(detail.progress),
            "pieces": f"{detail.pieces_have} / {detail.pieces_total}" if detail.pieces_total else "—",
            "piece_size": format_size(detail.piece_size, lang) if detail.piece_size else "—",
            "path": detail.save_path or "—",
            "downloaded": format_size(detail.downloaded, lang),
            "uploaded": format_size(detail.uploaded, lang),
            "ratio": f"{detail.ratio:.2f}",
            "availability": f"{detail.availability:.2f}" if detail.availability >= 0 else "—",
            "creator": detail.creator or "—",
            "comment": detail.comment or "—",
        }
        for key, value in values.items():
            self._show_general_value(key, value)
        self._fit_general()

    def _show_general_value(self, key: str, text: str) -> None:
        name = self.general_names[key]
        value = self.general_values[key]
        optional = key in ("error", "info_hash_v2", "creator", "comment")
        if optional and text in ("", "—"):
            name.hide()
            value.hide()
            return
        name.show()
        value.show()
        value.setToolTip("" if text == "—" else text)
        width = value.width()
        if width < 48:
            shown = text
        else:
            shown = value.fontMetrics().elidedText(text, Qt.TextElideMode.ElideMiddle, width - 8)
        if value.text() != shown:
            value.setText(shown)

    def _fit_general(self) -> None:
        height = self.general_grid.totalMinimumSize().height()
        if self.general_page.minimumHeight() != height:
            self.general_page.setMinimumHeight(height)

    def _sync_files(self, detail: TorrentDetails) -> None:
        if not detail.has_metadata:
            self.files_placeholder.setVisible(True)
            self.files_tree.setVisible(False)
            self.files_tree.clear()
            self._file_items.clear()
            self._files_sig = None
            return
        self.files_placeholder.setVisible(False)
        self.files_tree.setVisible(True)
        signature = (detail.id, tuple((item.index, item.path, item.size) for item in detail.files))
        if signature != self._files_sig:
            self._rebuild_files(detail)
            self._files_sig = signature
        else:
            self._update_file_rows(detail)

    def _rebuild_files(self, detail: TorrentDetails) -> None:
        self._files_block = True
        self.files_tree.clear()
        self._file_items.clear()
        nodes: dict[str, QTreeWidgetItem] = {}

        def ensure_folder(parts: list[str]) -> QTreeWidgetItem:
            key = "/".join(parts)
            if key in nodes:
                return nodes[key]
            item = QTreeWidgetItem([parts[-1], "", ""])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
            item.setCheckState(0, Qt.CheckState.Checked)
            item.setData(0, Qt.ItemDataRole.UserRole, -1)
            self._color_file_item(item)
            if len(parts) == 1:
                self.files_tree.addTopLevelItem(item)
            else:
                ensure_folder(parts[:-1]).addChild(item)
            nodes[key] = item
            return item

        lang = self.i18n.lang
        for info in detail.files:
            parts = [part for part in info.path.split("/") if part] or [info.path]
            parent = None
            if len(parts) > 1:
                parent = ensure_folder(parts[:-1])
            item = QTreeWidgetItem([parts[-1], format_size(info.size, lang), format_percent(info.progress)])
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(0, Qt.CheckState.Checked if info.priority > 0 else Qt.CheckState.Unchecked)
            item.setData(0, Qt.ItemDataRole.UserRole, info.index)
            self._color_file_item(item)
            if parent is None:
                self.files_tree.addTopLevelItem(item)
            else:
                parent.addChild(item)
            self._file_items[info.index] = item
        self.files_tree.expandToDepth(1)
        self._files_block = False

    def _update_file_rows(self, detail: TorrentDetails) -> None:
        self._files_block = True
        for info in detail.files:
            item = self._file_items.get(info.index)
            if item is None:
                continue
            progress = format_percent(info.progress)
            if item.text(2) != progress:
                item.setText(2, progress)
            self._color_file_item(item)
            state = Qt.CheckState.Checked if info.priority > 0 else Qt.CheckState.Unchecked
            if item.checkState(0) != state:
                item.setCheckState(0, state)
        self._files_block = False

    def _color_file_item(self, item: QTreeWidgetItem) -> None:
        brush = QBrush(QColor(self.theme.colors["text"]))
        for column in range(item.columnCount()):
            item.setForeground(column, brush)

    def _on_file_changed(self, item: QTreeWidgetItem, _column: int) -> None:
        if self._files_block:
            return
        tid = self.current_id()
        if not tid:
            return
        index = item.data(0, Qt.ItemDataRole.UserRole)
        checked = item.checkState(0) == Qt.CheckState.Checked
        if not isinstance(index, int) or index < 0:
            updates: dict[int, int] = {}

            def walk(node: QTreeWidgetItem) -> None:
                child_index = node.data(0, Qt.ItemDataRole.UserRole)
                if isinstance(child_index, int) and child_index >= 0:
                    updates[child_index] = 4 if checked else 0
                for child_number in range(node.childCount()):
                    walk(node.child(child_number))

            for child_number in range(item.childCount()):
                walk(item.child(child_number))
            if updates:
                self.engine.set_priorities(tid, updates)
            return
        self.engine.set_file_priority(tid, index, 4 if checked else 0)

    def _fill_trackers(self, detail: TorrentDetails) -> None:
        headers = [
            self.i18n.t("address"),
            self.i18n.t("status"),
            self.i18n.t("seeds"),
            self.i18n.t("peers"),
            self.i18n.t("message"),
        ]
        rows = []
        for tracker in detail.trackers:
            seeds = "—" if tracker.seeds < 0 else str(tracker.seeds)
            peers = "—" if tracker.peers < 0 else str(tracker.peers)
            rows.append([tracker.url, self.i18n.t(tracker.status_key), seeds, peers, self.i18n.t(tracker.message) if tracker.message else ""])
        _fill_table(self.trackers_table, headers, rows)

    def _fill_peers(self, detail: TorrentDetails) -> None:
        headers = [
            self.i18n.t("address"),
            self.i18n.t("client"),
            self.i18n.t("progress"),
            self.i18n.t("download"),
            self.i18n.t("upload"),
        ]
        lang = self.i18n.lang
        rows = [
            [
                peer.address,
                peer.client,
                format_percent(peer.progress),
                format_speed(peer.down_rate, lang),
                format_speed(peer.up_rate, lang),
            ]
            for peer in detail.peers
        ]
        _fill_table(self.peers_table, headers, rows)

    def _reveal(self, path: Path) -> None:
        if path.is_file():
            subprocess.Popen(["explorer", f"/select,{path}"])
            return
        target = path if path.is_dir() else path.parent
        if target.is_dir():
            os.startfile(target)

    def keyPressEvent(self, event) -> None:
        focus = QApplication.focusWidget()
        if isinstance(focus, (QLineEdit,)):
            super().keyPressEvent(event)
            return
        if event.key() == Qt.Key.Key_Space and self.view.hasFocus():
            ids = self.selected_ids()
            rows = [self.model.row_by_id(tid) for tid in ids]
            if any(row and not row.paused for row in rows):
                self.pause_selected()
            else:
                self.resume_selected()
            return
        if event.key() == Qt.Key.Key_Delete and self.view.hasFocus():
            self.remove_selected(False)
            return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if _drop_items(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:
        if _drop_items(event):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        items = _drop_items(event)
        if not items:
            event.ignore()
            return
        event.acceptProposedAction()
        self.open_inputs(items)

    def closeEvent(self, event: QCloseEvent) -> None:
        self.timer.stop()
        self.settings.geometry = bytes(self.saveGeometry().toBase64()).decode("ascii")
        self.settings.details_visible = self.act_details.isChecked()
        self.settings.save()
        self.engine.shutdown()
        event.accept()


def _fill_table(table: QTableWidget, headers: list[str], rows: list[list[str]]) -> None:
    table.setUpdatesEnabled(False)
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setRowCount(len(rows))
    for row_index, row in enumerate(rows):
        for column, value in enumerate(row):
            item = table.item(row_index, column)
            if item is None:
                item = QTableWidgetItem(value)
                item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                table.setItem(row_index, column, item)
            elif item.text() != value:
                item.setText(value)
    table.setUpdatesEnabled(True)


def _drop_items(event) -> list[str]:
    items: list[str] = []
    mime = event.mimeData()
    if mime.hasUrls():
        for url in mime.urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if path.lower().endswith(".torrent"):
                    items.append(path)
            elif url.toString().startswith("magnet:?"):
                items.append(url.toString())
    text = mime.text().strip() if mime.hasText() else ""
    if text.startswith("magnet:?") and text not in items:
        items.append(text)
    return items
