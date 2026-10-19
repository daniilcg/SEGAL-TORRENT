from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRect, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QStyle, QStyledItemDelegate

from segal_torrent.engine import TorrentRow
from segal_torrent.formatutil import format_eta_value, format_percent, format_size, format_speed
from segal_torrent.i18n import I18n
from segal_torrent.theme import Theme, bar_color, status_color

HEADERS = (
    "name",
    "size",
    "progress",
    "status",
    "download",
    "upload",
    "eta",
    "peers",
    "seeds",
)


class TorrentModel(QAbstractTableModel):
    def __init__(self, i18n: I18n, theme: Theme) -> None:
        super().__init__()
        self.i18n = i18n
        self.theme = theme
        self._rows: list[TorrentRow] = []

    @property
    def rows(self) -> list[TorrentRow]:
        return self._rows

    def row_by_id(self, tid: str) -> TorrentRow | None:
        for row in self._rows:
            if row.id == tid:
                return row
        return None

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        if parent.isValid():
            return 0
        return len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        return len(HEADERS)

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            if 0 <= section < len(HEADERS):
                return self.i18n.t(HEADERS[section])
        return None

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        row = self._rows[index.row()]
        column = index.column()
        lang = self.i18n.lang
        if role == Qt.ItemDataRole.DisplayRole:
            return self._text(row, column, lang)
        if role == Qt.ItemDataRole.UserRole:
            return self._sort_value(row, column)
        if role == Qt.ItemDataRole.UserRole + 1:
            return row.status_key
        if role == Qt.ItemDataRole.ToolTipRole:
            if column == 3 and row.error:
                return row.error
            if column == 0:
                return row.name
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if column in (0, 3):
                return Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
            return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        if role == Qt.ItemDataRole.ForegroundRole and column == 3:
            return QColor(status_color(row.status_key, self.theme.colors))
        if role == Qt.ItemDataRole.ForegroundRole and column in (4, 5):
            rate = row.down_rate if column == 4 else row.up_rate
            if rate <= 0:
                return QColor(self.theme.colors["text_muted"])
        return None

    def _text(self, row: TorrentRow, column: int, lang: str) -> str:
        if column == 0:
            return row.name
        if column == 1:
            return "—" if row.size <= 0 else format_size(row.size, lang)
        if column == 2:
            return format_percent(row.progress)
        if column == 3:
            return self.i18n.t(f"status_{row.status_key}")
        if column == 4:
            return format_speed(row.down_rate, lang)
        if column == 5:
            return format_speed(row.up_rate, lang)
        if column == 6:
            return format_eta_value(row.eta, lang)
        if column == 7:
            return str(row.peers)
        if column == 8:
            return str(row.seeds)
        return ""

    def _sort_value(self, row: TorrentRow, column: int):
        values = (
            row.name.casefold(),
            row.size,
            row.progress,
            row.status_key,
            row.down_rate,
            row.up_rate,
            row.eta if row.eta >= 0 else 10**12,
            row.peers,
            row.seeds,
        )
        return values[column]

    def sync(self, rows: list[TorrentRow]) -> None:
        incoming = {row.id: row for row in rows}
        index = 0
        while index < len(self._rows):
            if self._rows[index].id not in incoming:
                self.beginRemoveRows(QModelIndex(), index, index)
                self._rows.pop(index)
                self.endRemoveRows()
            else:
                index += 1
        known = {row.id for row in self._rows}
        for row in rows:
            if row.id not in known:
                self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
                self._rows.append(row)
                self.endInsertRows()
        by_id = {row.id: row for row in rows}
        changed = False
        for index, old in enumerate(self._rows):
            new = by_id.get(old.id)
            if new is not None and new != old:
                self._rows[index] = new
                changed = True
        if changed and self._rows:
            top = self.index(0, 0)
            bottom = self.index(len(self._rows) - 1, self.columnCount() - 1)
            self.dataChanged.emit(top, bottom)

    def retranslate(self) -> None:
        self.headerDataChanged.emit(Qt.Orientation.Horizontal, 0, self.columnCount() - 1)
        if self._rows:
            top = self.index(0, 0)
            bottom = self.index(len(self._rows) - 1, self.columnCount() - 1)
            self.dataChanged.emit(top, bottom)


class ProgressDelegate(QStyledItemDelegate):
    def __init__(self, theme: Theme, parent=None) -> None:
        super().__init__(parent)
        self.theme = theme

    def paint(self, painter: QPainter, option, index: QModelIndex) -> None:
        colors = self.theme.colors
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, QColor(colors["selection"]))
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.fillRect(option.rect, QColor(colors["hover"]))
        progress = index.data(Qt.ItemDataRole.UserRole)
        try:
            ratio = max(0.0, min(1.0, float(progress)))
        except (TypeError, ValueError):
            ratio = 0.0
        key = index.data(Qt.ItemDataRole.UserRole + 1) or "downloading"
        rect = option.rect
        bar = QRect(rect.left() + 10, rect.center().y() - 4, max(24, rect.width() - 64), 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(colors["track"]))
        painter.drawRoundedRect(bar, 3, 3)
        fill_width = int(bar.width() * ratio)
        if ratio > 0 and fill_width < 4:
            fill_width = 4
        fill_width = min(fill_width, bar.width())
        if fill_width > 0:
            painter.setBrush(QColor(bar_color(str(key), colors)))
            painter.drawRoundedRect(QRect(bar.left(), bar.top(), fill_width, bar.height()), 3, 3)
        text = format_percent(ratio)
        text_rect = QRect(bar.right() + 6, rect.top(), rect.right() - bar.right() - 8, rect.height())
        painter.setPen(QColor(colors["selection_text"] if option.state & QStyle.StateFlag.State_Selected else colors["text"]))
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, text)
        painter.restore()

    def sizeHint(self, option, index):
        hint = super().sizeHint(option, index)
        hint.setHeight(40)
        return hint
