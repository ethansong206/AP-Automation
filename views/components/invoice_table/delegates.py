from __future__ import annotations

from typing import Optional, Tuple

from PyQt5.QtCore import Qt, QModelIndex, QRect, QPoint, QSortFilterProxyModel, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPen, QBrush, QPalette, QPainter
from PyQt5.QtWidgets import (
    QStyledItemDelegate, QStyleOptionViewItem, QLineEdit, QStyle, QApplication, QStyleOptionButton
)

from .model import C_VENDOR, BODY_COLS, C_SELECT


class BodyEditDelegate(QStyledItemDelegate):
    """Opaque in-place editor + ensure model-provided BackgroundRole wins."""
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setAutoFillBackground(True)
        editor.setStyleSheet("background:#FFFFFF; color:#000000; padding:0 4px; margin:0;")
        editor.setFrame(False)
        return editor

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        opt = QStyleOptionViewItem(option)
        if opt.state & QStyle.State_Editing:
            painter.save()
            painter.fillRect(opt.rect, opt.palette.base())
            painter.restore()
            return

        self.initStyleOption(opt, index)

        bgdata = index.data(Qt.BackgroundRole)
        brush = None
        if isinstance(bgdata, QColor):
            brush = QBrush(bgdata)
        elif isinstance(bgdata, QBrush):
            brush = bgdata

        if brush is not None:
            painter.save()
            painter.fillRect(opt.rect, brush)
            painter.restore()
            opt.backgroundBrush = brush
            opt.palette.setBrush(QPalette.Base, brush)
            opt.palette.setBrush(QPalette.AlternateBase, brush)

        QStyledItemDelegate.paint(self, painter, opt, index)

        # Vendor-only left stripe on top (unchanged)
        if index.column() == C_VENDOR:
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

        # Column divider
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


class SelectCheckboxDelegate(QStyledItemDelegate):
    """
    Centers a single checkbox indicator in the cell and handles clicks.
    Eliminates the phantom text box next to the checkbox.
    """
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        # Let BackgroundRole paint first
        bg = index.data(Qt.BackgroundRole)
        if isinstance(bg, (QBrush, QColor)):
            painter.save()
            painter.fillRect(option.rect, bg)
            painter.restore()

        style = option.widget.style() if option.widget else QApplication.style()
        chk = QStyleOptionButton()
        chk.state = QStyle.State_Enabled
        state = index.data(Qt.CheckStateRole)
        if state == Qt.Checked:
            chk.state |= QStyle.State_On
        else:
            chk.state |= QStyle.State_Off

        # Indicator size from style metrics; center in the cell
        w = style.pixelMetric(QStyle.PM_IndicatorWidth, chk, option.widget)
        h = style.pixelMetric(QStyle.PM_IndicatorHeight, chk, option.widget)
        x = option.rect.x() + (option.rect.width() - w) // 2
        y = option.rect.y() + (option.rect.height() - h) // 2
        chk.rect = QRect(x, y, w, h)

        # Draw only the checkbox indicator (no text)
        painter.save()
        style.drawPrimitive(QStyle.PE_IndicatorCheckBox, chk, painter, option.widget)
        painter.restore()

        # Optional: draw right divider line
        try:
            last_col = index.model().columnCount() - 1
        except Exception:
            last_col = 0
        if index.column() < last_col:
            painter.save()
            pen = QPen(QColor("#D0D6DF"))
            painter.setPen(pen)
            rx = option.rect.right()
            painter.drawLine(rx, option.rect.top() + 1, rx, option.rect.bottom() - 1)
            painter.restore()

    def editorEvent(self, event, model, option, index):
        if event.type() == event.MouseButtonRelease and event.button() == Qt.LeftButton:
            # Toggle on any click within the cell (no tiny hitbox)
            src_model = model
            src_index = index
            if isinstance(model, QSortFilterProxyModel):
                src_model = model.sourceModel()
                src_index = model.mapToSource(index)

            current = src_model.index(src_index.row(), C_SELECT)
            cur_state = src_model.data(current, Qt.CheckStateRole)
            new_state = Qt.Unchecked if cur_state == Qt.Checked else Qt.Checked
            return src_model.setData(current, new_state, Qt.CheckStateRole)
        return super().editorEvent(event, model, option, index)


class FlagDelegate(QStyledItemDelegate):
    """Legacy: clickable flag icon in a dedicated column (unused now)."""
    # kept for compatibility; not installed anywhere
    pass


class ActionsDelegate(QStyledItemDelegate):
    """Three click targets: ⚑ (Flag), ✎ (Manual Entry), ✖ (Delete)."""
    editClicked = pyqtSignal(int)    # source row
    deleteClicked = pyqtSignal(int)  # source row

    def __init__(self, parent=None, icon_font: Optional[QFont] = None):
        super().__init__(parent)
        self._icon_font = icon_font

    def _thirds(self, rect: QRect) -> Tuple[QRect, QRect, QRect]:
        w = rect.width()
        h = rect.height()
        pad = max(4, int(h * 0.15))
        slot = (w - 2 * pad) // 3
        left = QRect(rect.left(), rect.top(), slot, h)
        mid = QRect(left.right() + pad, rect.top(), slot, h)
        right = QRect(mid.right() + pad, rect.top(), max(slot, rect.right() - (mid.right() + pad)), h)
        return left, mid, right

    def editorEvent(self, event, model, option, index):
        if event.type() == event.MouseButtonRelease and event.button() == Qt.LeftButton:
            src_model = model
            src_index = index
            if isinstance(model, QSortFilterProxyModel):
                src_model = model.sourceModel()
                src_index = model.mapToSource(index)

            left, mid, right = self._thirds(option.rect)
            pos: QPoint = event.pos()
            if left.contains(pos):
                # Toggle flag
                cur = src_model.get_flag(src_index.row())
                src_model.set_flag(src_index.row(), not cur)
                return True
            if mid.contains(pos):
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

        # Determine flag state
        model = index.model()
        src_model = model
        src_index = index
        if isinstance(model, QSortFilterProxyModel):
            src_model = model.sourceModel()
            src_index = model.mapToSource(index)
        flagged = False
        try:
            flagged = bool(src_model.get_flag(src_index.row()))
        except Exception:
            pass

        left, mid, right = self._thirds(option.rect)

        # Draw flag (first)
        painter.drawText(left, Qt.AlignCenter, "⚑" if flagged else "⚐")
        # Draw edit (second)
        painter.setPen(QPen(QColor("#000000")))
        painter.drawText(mid, Qt.AlignCenter, "✎")
        # Draw delete (third)
        painter.setPen(QPen(QColor("#D11A2A")))
        painter.drawText(right, Qt.AlignCenter, "✖")

        painter.restore()

        # Divider
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
