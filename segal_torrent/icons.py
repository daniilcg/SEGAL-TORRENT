from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def toolbar_icon(kind: str, color: str, size: int = 18) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    pen = QPen(QColor(color), 1.7, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    if kind == "plus":
        painter.drawLine(9, 3, 9, 15)
        painter.drawLine(3, 9, 15, 9)
    elif kind == "pause":
        painter.drawLine(6, 3, 6, 15)
        painter.drawLine(12, 3, 12, 15)
    elif kind == "play":
        path = QPainterPath()
        path.moveTo(5, 3)
        path.lineTo(14, 9)
        path.lineTo(5, 15)
        path.closeSubpath()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPath(path)
    elif kind == "trash":
        painter.drawLine(4, 5, 14, 5)
        painter.drawLine(7, 3, 11, 3)
        painter.drawRoundedRect(5, 6, 8, 9, 1.2, 1.2)
        painter.drawLine(8, 8, 8, 13)
        painter.drawLine(10, 8, 10, 13)
    elif kind == "folder":
        path = QPainterPath()
        path.moveTo(2, 6)
        path.lineTo(2, 15)
        path.lineTo(16, 15)
        path.lineTo(16, 5)
        path.lineTo(8, 5)
        path.lineTo(7, 3)
        path.lineTo(2, 3)
        path.closeSubpath()
        painter.drawPath(path)
    elif kind == "magnet":
        painter.drawLine(5, 2, 5, 8)
        painter.drawLine(13, 2, 13, 8)
        painter.drawLine(5, 2, 7, 2)
        painter.drawLine(11, 2, 13, 2)
        painter.drawArc(3, 5, 12, 10, 180 * 16, 180 * 16)
    elif kind == "sun":
        painter.drawEllipse(6, 6, 6, 6)
        for step in range(8):
            angle = step * math.pi / 4
            painter.drawLine(
                int(9 + math.cos(angle) * 5),
                int(9 + math.sin(angle) * 5),
                int(9 + math.cos(angle) * 8),
                int(9 + math.sin(angle) * 8),
            )
    elif kind == "moon":
        path = QPainterPath()
        path.setFillRule(Qt.FillRule.OddEvenFill)
        path.addEllipse(2, 2, 14, 14)
        path.addEllipse(7, 2, 12, 14)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawPath(path)
    painter.end()
    return QIcon(pix)
