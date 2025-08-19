from __future__ import annotations

from typing import Optional, Tuple

from PyQt5.QtCore import Qt, QModelIndex, QRect, QPoint, QSortFilterProxyModel, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPen, QBrush, QPalette, QPainter
from PyQt5.QtWidgets import QStyledItemDelegate, QStyleOptionViewItem, QLineEdit, QStyle

from .model import C_VENDOR, BODY_COLS


class BodyEditDelegate(QStyledItemDelegate):
    """Opaque in-place editor + ensure model-provided BackgroundRole wins.
    Paint order: 1) base/zebra, 2) model highlight, 3) text, 4) stripe/divider.
    """
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setAutoFillBackground(True)
        editor.setStyleSheet("background:#FFFFFF; color:#000000; padding:0 4px; margin:0;")
        editor.setFrame(False)
        return editor

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        opt = QStyleOptionViewItem(option)
        # If currently editing, don't draw underlying text/stripe; let editor show cleanly
        if opt.state & QStyle.State_Editing:
            painter.save()
            painter.fillRect(opt.rect, opt.palette.base())
            painter.restore()
            return

        # 1) Initialize style option to let Qt compute zebra/selection etc.
        self.initStyleOption(opt, index)

        # 2) If model provides a background, apply it explicitly so it overrides zebra
        bgdata = index.data(Qt.BackgroundRole)
        brush = None
        if isinstance(bgdata, QColor):
            brush = QBrush(bgdata)
        elif isinstance(bgdata, QBrush):
            brush = bgdata

        if brush is not None:
            # Pre-fill with our highlight to guarantee visibility
            painter.save()
            painter.fillRect(opt.rect, brush)
            painter.restore()
            # Also set both backgroundBrush and palette so default painting doesn't undo it
            opt.backgroundBrush = brush
            opt.palette.setBrush(QPalette.Base, brush)
            opt.palette.setBrush(QPalette.AlternateBase, brush)

        # 3) Default painting (text, focus, etc.)
        QStyledItemDelegate.paint(self, painter, opt, index)

        # 4) Vendor-only left stripe on top
        if index.column() == C_VENDOR:
            # Map to source to inspect entire row
            model = index.model()
            src_model = model
            src_index = index
            if isinstance(model, QSortFilterProxyModel):
                src_model = model.sourceModel()
                src_index = model.mapToSource(index)
            r = src_index.row()
            vals = src_model.row_values(r)
            filled = [bool(str(v).strip()) for v in vals]
            any_empty = any(not f for f in filled)
            all_empty = not any(filled)
            if any_empty and not all_empty:
                painter.save()
                painter.fillRect(QRect(option.rect.left(), option.rect.top(), 3, option.rect.height()), QColor("#FFEB80"))
                painter.restore()

        # Vertical divider between columns (no divider after last column)
        try:
            last_col = index.model().columnCount() - 1
        except Exception:
            last_col = 0
        if index.column() < last_col:
            painter.save()
            pen = QPen(QColor("#D0D6DF"))
            painter.setPen(pen)
            x = option.rect.right()
            painter.drawLine(x, option.rect.top() + 1, x, option.rect.bottom() - 1)
            painter.restore()


class FlagDelegate(QStyledItemDelegate):
    """Clickable flag icon in column 0."""
    def __init__(self, parent=None, icon_font: Optional[QFont] = None):
        super().__init__(parent)
        self._icon_font = icon_font

    def editorEvent(self, event, model, option, index):
        if event.type() == event.MouseButtonRelease and event.button() == Qt.LeftButton:
            src_model = model
            src_index = index
            if isinstance(model, QSortFilterProxyModel):
                src_model = model.sourceModel()
                src_index = model.mapToSource(index)
            flag = src_model.get_flag(src_index.row())
            src_model.set_flag(src_index.row(), not flag)
            return True
        return super().editorEvent(event, model, option, index)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        if self._icon_font is not None:
            painter.setFont(self._icon_font)
        text = index.data(Qt.DisplayRole) or ""
        painter.drawText(option.rect, Qt.AlignCenter, text)
        painter.restore()
        # Divider after paint so it sits on top
        try:
            last_col = index.model().columnCount() - 1
        except Exception:
            last_col = 0
        if index.column() < last_col:
            painter.save()
            pen = QPen(QColor("#D0D6DF"))
            painter.setPen(pen)
            x = option.rect.right()
            painter.drawLine(x, option.rect.top() + 1, x, option.rect.bottom() - 1)
            painter.restore()


class ActionsDelegate(QStyledItemDelegate):
    """Two click targets in one cell: ✎ (Manual Entry) and ✖ (Delete)."""
    editClicked = pyqtSignal(int)    # source row
    deleteClicked = pyqtSignal(int)  # source row

    def __init__(self, parent=None, icon_font: Optional[QFont] = None):
        super().__init__(parent)
        self._icon_font = icon_font

    def _split_rects(self, rect: QRect) -> Tuple[QRect, QRect]:
        w = rect.width()
        h = rect.height()
        pad = max(4, int(h * 0.15))
        half = (w - pad) // 2
        left = QRect(rect.left() + pad // 2, rect.top(), half, h)
        right = QRect(left.right() + pad, rect.top(), half, h)
        return left, right

    def editorEvent(self, event, model, option, index):
        if event.type() == event.MouseButtonRelease and event.button() == Qt.LeftButton:
            src_model = model
            src_index = index
            if isinstance(model, QSortFilterProxyModel):
                src_model = model.sourceModel()
                src_index = model.mapToSource(index)

            left, right = self._split_rects(option.rect)
            pos: QPoint = event.pos()
            if left.contains(pos):
                self.editClicked.emit(src_index.row())
                return True
            if right.contains(pos):
                self.deleteClicked.emit(src_index.row())
                return True
        return super().editorEvent(event, model, option, index)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        painter.save()
        if self._icon_font is not None:
            painter.setFont(self._icon_font)
        left, right = self._split_rects(option.rect)
        painter.drawText(left, Qt.AlignCenter, "✎")
        pen = QPen(QColor("#D11A2A"))
        painter.setPen(pen)
        painter.drawText(right, Qt.AlignCenter, "✖")
        painter.restore()
        # Divider after paint so it sits on top
        try:
            last_col = index.model().columnCount() - 1
        except Exception:
            last_col = 0
        if index.column() < last_col:
            painter.save()
            pen = QPen(QColor("#D0D6DF"))
            painter.setPen(pen)
            x = option.rect.right()
            painter.drawLine(x, option.rect.top() + 1, x, option.rect.bottom() - 1)
            painter.restore()