from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

import libtorrent as lt

from segal_torrent import __author__, __url__, __version__
from segal_torrent.engine import TorrentPreview
from segal_torrent.formatutil import format_size
from segal_torrent.i18n import I18n
from segal_torrent.paths import asset
from segal_torrent.settings_store import Settings


def _buttons(dialog: QDialog, i18n: I18n, ok_text: str) -> QDialogButtonBox:
    box = QDialogButtonBox(dialog)
    ok = box.addButton(ok_text, QDialogButtonBox.ButtonRole.AcceptRole)
    cancel = box.addButton(i18n.t("cancel"), QDialogButtonBox.ButtonRole.RejectRole)
    ok.setObjectName("primary")
    ok.setDefault(True)
    box.accepted.connect(dialog.accept)
    box.rejected.connect(dialog.reject)
    cancel.setAutoDefault(False)
    return box


def _file_nodes(files, lang: str) -> QTreeWidgetItem:
    root_holder: dict[str, QTreeWidgetItem] = {}

    def ensure(parent: QTreeWidgetItem | None, parts: list[str]) -> QTreeWidgetItem:
        key = "/".join(parts)
        if key in root_holder:
            return root_holder[key]
        item = QTreeWidgetItem([parts[-1], "", ""])
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable | Qt.ItemFlag.ItemIsAutoTristate)
        item.setCheckState(0, Qt.CheckState.Checked)
        item.setData(0, Qt.ItemDataRole.UserRole, -1)
        if parent is None:
            pass
        else:
            parent.addChild(item)
        root_holder[key] = item
        return item

    top_items: list[QTreeWidgetItem] = []
    for info in files:
        parts = [part for part in info.path.split("/") if part]
        if not parts:
            parts = [info.path or str(info.index)]
        parent = None
        for depth in range(len(parts) - 1):
            item = ensure(parent, parts[: depth + 1])
            if parent is None and item not in top_items:
                top_items.append(item)
            parent = item
        leaf = QTreeWidgetItem([parts[-1], format_size(info.size, lang), ""])
        leaf.setFlags(leaf.flags() | Qt.ItemFlag.ItemIsUserCheckable)
        leaf.setCheckState(0, Qt.CheckState.Checked)
        leaf.setData(0, Qt.ItemDataRole.UserRole, info.index)
        leaf.setData(0, Qt.ItemDataRole.UserRole + 1, info.size)
        if parent is None:
            top_items.append(leaf)
        else:
            parent.addChild(leaf)
    ghost = QTreeWidgetItem()
    for item in top_items:
        ghost.addChild(item)
    return ghost


class AddTorrentDialog(QDialog):
    def __init__(self, preview: TorrentPreview, folder: str, start: bool, i18n: I18n, parent=None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self.preview = preview
        self.setMinimumSize(680, 520)
        self.resize(720, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)

        title = QLabel(preview.name)
        title.setObjectName("title")
        title.setWordWrap(True)
        layout.addWidget(title)

        meta = QLabel(format_size(preview.size, i18n.lang))
        meta.setObjectName("dim")
        if preview.creator:
            meta.setText(f"{format_size(preview.size, i18n.lang)}  ·  {preview.creator}")
        layout.addWidget(meta)
        if preview.comment:
            comment = QLabel(preview.comment)
            comment.setObjectName("dim")
            comment.setWordWrap(True)
            layout.addWidget(comment)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([i18n.t("file_col"), i18n.t("size"), ""])
        self.tree.setColumnWidth(0, 420)
        self.tree.setColumnWidth(1, 100)
        self.tree.setRootIsDecorated(True)
        ghost = _file_nodes(preview.files, i18n.lang)
        while ghost.childCount():
            self.tree.addTopLevelItem(ghost.takeChild(0))
        self.tree.expandToDepth(1)
        self.tree.itemChanged.connect(self._refresh_selected)
        layout.addWidget(self.tree, 1)

        row = QHBoxLayout()
        self.all_btn = QPushButton(i18n.t("select_all"))
        self.none_btn = QPushButton(i18n.t("select_none"))
        self.all_btn.clicked.connect(lambda: self._set_all(Qt.CheckState.Checked))
        self.none_btn.clicked.connect(lambda: self._set_all(Qt.CheckState.Unchecked))
        self.selected_label = QLabel()
        self.selected_label.setObjectName("dim")
        row.addWidget(self.all_btn)
        row.addWidget(self.none_btn)
        row.addStretch(1)
        row.addWidget(self.selected_label)
        layout.addLayout(row)

        path_row = QHBoxLayout()
        path_label = QLabel(i18n.t("save_path"))
        self.path_edit = QLineEdit(folder)
        browse = QPushButton(i18n.t("browse"))
        browse.clicked.connect(self._browse)
        path_row.addWidget(path_label)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        layout.addLayout(path_row)

        self.start_box = QCheckBox(i18n.t("start_now"))
        self.start_box.setChecked(start)
        self.seq_box = QCheckBox(i18n.t("sequential"))
        layout.addWidget(self.start_box)
        layout.addWidget(self.seq_box)

        self._buttons = _buttons(self, i18n, i18n.t("add"))
        layout.addWidget(self._buttons)
        self.setWindowTitle(i18n.t("add_torrent"))
        self._refresh_selected()

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self.i18n.t("choose_folder"), self.path_edit.text())
        if folder:
            self.path_edit.setText(folder)

    def _set_all(self, state: Qt.CheckState) -> None:
        self.tree.blockSignals(True)

        def walk(item: QTreeWidgetItem) -> None:
            item.setCheckState(0, state)
            for index in range(item.childCount()):
                walk(item.child(index))

        for index in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(index))
        self.tree.blockSignals(False)
        self._refresh_selected()

    def _checked_size(self) -> tuple[set[int], int]:
        selected: set[int] = set()
        total = 0

        def walk(item: QTreeWidgetItem) -> None:
            nonlocal total
            index = item.data(0, Qt.ItemDataRole.UserRole)
            if isinstance(index, int) and index >= 0 and item.checkState(0) == Qt.CheckState.Checked:
                selected.add(index)
                size = item.data(0, Qt.ItemDataRole.UserRole + 1) or 0
                total += int(size)
            for child_index in range(item.childCount()):
                walk(item.child(child_index))

        for index in range(self.tree.topLevelItemCount()):
            walk(self.tree.topLevelItem(index))
        return selected, total

    def _refresh_selected(self, *_args) -> None:
        _selected, total = self._checked_size()
        self.selected_label.setText(self.i18n.t("selected", size=format_size(total, self.i18n.lang)))
        ok = self._buttons.buttons()[0] if False else None
        for button in self._buttons.buttons():
            if button.objectName() == "primary":
                ok = button
        if ok is not None:
            ok.setEnabled(total > 0 or not self.preview.files)

    def values(self) -> tuple[str, set[int], bool, bool] | None:
        selected, total = self._checked_size()
        if self.preview.files and total <= 0:
            QMessageBox.warning(self, self.i18n.t("error_title"), self.i18n.t("no_files"))
            return None
        return self.path_edit.text().strip(), selected, self.start_box.isChecked(), self.seq_box.isChecked()

    def accept(self) -> None:
        if self.values() is None:
            return
        super().accept()


class MagnetDialog(QDialog):
    def __init__(self, folder: str, start: bool, i18n: I18n, magnet: str = "", parent=None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(10)
        layout.addWidget(QLabel(i18n.t("magnet_prompt")))
        self.edit = QLineEdit(magnet)
        self.edit.setPlaceholderText(i18n.t("magnet_placeholder"))
        layout.addWidget(self.edit)
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(folder)
        browse = QPushButton(i18n.t("browse"))
        browse.clicked.connect(self._browse)
        path_row.addWidget(QLabel(i18n.t("save_path")))
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        layout.addLayout(path_row)
        self.start_box = QCheckBox(i18n.t("start_now"))
        self.start_box.setChecked(start)
        layout.addWidget(self.start_box)
        layout.addWidget(_buttons(self, i18n, i18n.t("add")))
        self.setWindowTitle(i18n.t("add_magnet"))

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self.i18n.t("choose_folder"), self.path_edit.text())
        if folder:
            self.path_edit.setText(folder)

    def accept(self) -> None:
        uri = self.edit.text().strip()
        try:
            parsed = lt.parse_magnet_uri(uri)
            if parsed.info_hashes.v1.is_all_zeros() and parsed.info_hashes.v2.is_all_zeros():
                raise ValueError("missing hash")
        except Exception:
            QMessageBox.warning(self, self.i18n.t("error_title"), self.i18n.t("invalid_magnet"))
            return
        if not self.path_edit.text().strip():
            QMessageBox.warning(self, self.i18n.t("error_title"), self.i18n.t("folder_missing"))
            return
        super().accept()

    def values(self) -> tuple[str, str, bool]:
        return self.edit.text().strip(), self.path_edit.text().strip(), self.start_box.isChecked()


class SettingsDialog(QDialog):
    def __init__(self, settings: Settings, i18n: I18n, parent=None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self.setMinimumWidth(520)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.setSpacing(12)

        downloads = QGroupBox(i18n.t("downloads_group"))
        form = QFormLayout(downloads)
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit(settings.download_dir)
        browse = QPushButton(i18n.t("browse"))
        browse.clicked.connect(self._browse)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(browse)
        form.addRow(i18n.t("default_folder"), path_row)
        hint = QLabel(i18n.t("folder_hint"))
        hint.setObjectName("dim")
        hint.setWordWrap(True)
        form.addRow("", hint)
        self.start_box = QCheckBox(i18n.t("start_immediately"))
        self.start_box.setChecked(settings.start_immediately)
        form.addRow("", self.start_box)
        self.active = QSpinBox()
        self.active.setRange(1, 20)
        self.active.setValue(settings.active_downloads)
        form.addRow(i18n.t("active"), self.active)
        layout.addWidget(downloads)

        network = QGroupBox(i18n.t("network_group"))
        net = QFormLayout(network)
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(settings.listen_port if settings.listen_port else 6881)
        net.addRow(i18n.t("listen_port"), self.port)
        self.down = self._limit(settings.max_download_kb)
        self.up = self._limit(settings.max_upload_kb)
        net.addRow(i18n.t("max_down"), self.down)
        net.addRow(i18n.t("max_up"), self.up)
        layout.addWidget(network)

        interface = QGroupBox(i18n.t("interface_group"))
        face = QFormLayout(interface)
        self.language = QComboBox()
        self.language.addItem(i18n.t("english"), "en")
        self.language.addItem(i18n.t("russian"), "ru")
        self.language.setCurrentIndex(0 if settings.language != "ru" else 1)
        self.theme = QComboBox()
        self.theme.addItem(i18n.t("dark_theme"), "dark")
        self.theme.addItem(i18n.t("light_theme"), "light")
        self.theme.setCurrentIndex(0 if settings.theme != "light" else 1)
        face.addRow(i18n.t("language"), self.language)
        face.addRow(i18n.t("theme"), self.theme)
        default_button = QPushButton(i18n.t("default_app_button"))
        default_button.clicked.connect(self._make_default)
        face.addRow("", default_button)
        layout.addWidget(interface)

        layout.addWidget(_buttons(self, i18n, i18n.t("save")))
        self.setWindowTitle(i18n.t("settings"))

    def _limit(self, value: int) -> QSpinBox:
        spin = QSpinBox()
        spin.setRange(0, 1000000)
        spin.setSuffix(" KB/s" if self.i18n.lang != "ru" else " КБ/с")
        spin.setSpecialValueText(self.i18n.t("unlimited"))
        spin.setValue(max(0, value))
        return spin

    def _browse(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, self.i18n.t("choose_folder"), self.path_edit.text())
        if folder:
            self.path_edit.setText(folder)

    def _make_default(self) -> None:
        from segal_torrent.associations import open_default_ui, register

        try:
            register()
            open_default_ui()
        except Exception as exc:
            QMessageBox.warning(self, self.i18n.t("default_app_title"), str(exc))

    def values(self) -> dict:
        return {
            "download_dir": self.path_edit.text().strip(),
            "listen_port": self.port.value(),
            "max_download_kb": self.down.value(),
            "max_upload_kb": self.up.value(),
            "active_downloads": self.active.value(),
            "start_immediately": self.start_box.isChecked(),
            "language": self.language.currentData(),
            "theme": self.theme.currentData(),
        }


class PeerDialog(QDialog):
    def __init__(self, i18n: I18n, parent=None) -> None:
        super().__init__(parent)
        self.i18n = i18n
        self.setMinimumWidth(420)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 16)
        layout.addWidget(QLabel(i18n.t("peer_prompt")))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(i18n.t("peer_placeholder"))
        layout.addWidget(self.edit)
        layout.addWidget(_buttons(self, i18n, i18n.t("add")))
        self.setWindowTitle(i18n.t("connect_peer"))

    def accept(self) -> None:
        if self.endpoint() is None:
            QMessageBox.warning(self, self.i18n.t("error_title"), self.i18n.t("invalid_peer"))
            return
        super().accept()

    def endpoint(self) -> tuple[str, int] | None:
        text = self.edit.text().strip()
        if ":" not in text:
            return None
        host, _, port_text = text.rpartition(":")
        host = host.strip().strip("[]")
        try:
            port = int(port_text.strip())
        except ValueError:
            return None
        if not host or not (1 <= port <= 65535):
            return None
        return host, port


class AboutDialog(QDialog):
    def __init__(self, i18n: I18n, parent=None) -> None:
        super().__init__(parent)
        self.setMinimumWidth(460)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 18)
        layout.setSpacing(8)
        logo = QLabel()
        logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        path = asset("logo.png")
        if path.is_file():
            pix = QPixmap(str(path))
            logo.setPixmap(pix.scaledToWidth(420, Qt.TransformationMode.SmoothTransformation))
        layout.addWidget(logo)
        version = QLabel(i18n.t("about_version", version=__version__))
        version.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version.setObjectName("dim")
        text = QLabel(i18n.t("about_text"))
        text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        text.setWordWrap(True)
        dev = QLabel(f"{i18n.t('developer')}: {__author__}")
        dev.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link = QLabel(f'{i18n.t("website")}: <a href="{__url__}">segal.run</a>')
        link.setAlignment(Qt.AlignmentFlag.AlignCenter)
        link.setTextFormat(Qt.TextFormat.RichText)
        link.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        link.setOpenExternalLinks(True)
        link.setStyleSheet("color: #3574F0;")
        layout.addWidget(version)
        layout.addWidget(text)
        layout.addSpacing(8)
        layout.addWidget(dev)
        layout.addWidget(link)
        close = QPushButton(i18n.t("close"))
        close.setObjectName("primary")
        close.clicked.connect(self.accept)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(close)
        layout.addSpacing(8)
        layout.addLayout(row)
        self.setWindowTitle(i18n.t("about"))


def confirm_remove(parent: QWidget, i18n: I18n, names: list[str], delete_files: bool) -> bool:
    if len(names) == 1:
        key = "remove_delete" if delete_files else "remove_keep"
        text = i18n.t(key, name=names[0])
    else:
        key = "remove_delete_many" if delete_files else "remove_keep_many"
        text = i18n.t(key, count=len(names))
    box = QMessageBox(parent)
    box.setIcon(QMessageBox.Icon.Warning)
    box.setWindowTitle(i18n.t("remove_title"))
    box.setText(text)
    yes = box.addButton(
        i18n.t("delete_files_btn" if delete_files else "keep_files_btn"),
        QMessageBox.ButtonRole.DestructiveRole if delete_files else QMessageBox.ButtonRole.AcceptRole,
    )
    box.addButton(i18n.t("cancel"), QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return box.clickedButton() is yes
