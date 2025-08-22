from __future__ import annotations

from typing import Optional, Tuple

import sys, os
from PyQt5.QtCore import Qt, QModelIndex, QRect, QRectF, QPoint, QSortFilterProxyModel, pyqtSignal
from PyQt5.QtGui import QColor, QFont, QPen, QBrush, QPalette, QPainter, QIcon
from PyQt5.QtWidgets import (
    QStyledItemDelegate, QStyleOptionViewItem, QLineEdit, QStyle, QApplication, QStyleOptionButton
)

from .model import C_VENDOR, BODY_COLS, C_SELECT
from views.app_shell import _resolve_icon
from PyQt5.QtSvg import QSvgRenderer

def resource_path(*parts):
    """Return absolute path, working in dev and in PyInstaller .exe."""
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
    return os.path.join(base, *parts)


ASSETS_DIR = resource_path("assets", "icons")

class BodyEditDelegate(QStyledItemDelegate):
    """Opaque in-place editor + ensure model-provided BackgroundRole wins."""
    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setAutoFillBackground(True)
        # Match the delegate's left text margin so the editor aligns
        editor.setStyleSheet("background:#FFFFFF; color:#000000; padding:0 6px; margin:0;")
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

        # Nudge text rendering slightly to the right so it isn't flush
        # against the cell's left border (or vendor warning stripe).
        opt.rect.adjust(6, 0, 0, 0)

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
            flagged = False
            get_flag = getattr(src_model, "get_flag", None)
            if callable(get_flag):
                try:
                    flagged = bool(get_flag(r))
                except Exception:
                    pass

            if flagged:
                painter.save()
                painter.fillRect(QRect(option.rect.left(), option.rect.top(), 4, option.rect.height()), QColor("#FF9B9B"))
                painter.restore()
            else:
                vals = src_model.row_values(r)
                # Exclude shipping cost (index 6) from empty cell checks for yellow stripe
                filled = [bool(str(v).strip()) for i, v in enumerate(vals) if i != 6]
                any_empty = any(not f for f in filled)
                all_empty = not any(filled)
                if any_empty and not all_empty:
                    painter.save()
                    painter.fillRect(QRect(option.rect.left(), option.rect.top(), 4, option.rect.height()), QColor("#FFF1A6"))
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
    def __init__(self, parent=None):
        super().__init__(parent)
        self._svg_unchecked = QSvgRenderer(os.path.join(ASSETS_DIR, "checkbox_unchecked.svg"), self)
        self._svg_checked = QSvgRenderer(os.path.join(ASSETS_DIR, "checkbox_checked.svg"), self)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        # Let BackgroundRole paint first
        bg = index.data(Qt.BackgroundRole)
        if isinstance(bg, (QBrush, QColor)):
            painter.save()
            painter.fillRect(option.rect, bg)
            painter.restore()

        state = index.data(Qt.CheckStateRole)
        renderer = self._svg_checked if state == Qt.Checked else self._svg_unchecked

        # Size and center the SVG within the cell
        target_size = max(16, min(22, option.rect.height() - 8))
        box = QRect(0, 0, target_size, target_size)
        box.moveCenter(option.rect.center())

        painter.save()
        if renderer and renderer.isValid():
            renderer.render(painter, QRectF(box))
        else:
            # Fallback to default style
            style = option.widget.style() if option.widget else QApplication.style()
            chk = QStyleOptionButton()
            chk.state = QStyle.State_Enabled
            if state == Qt.Checked:
                chk.state |= QStyle.State_On
            else:
                chk.state |= QStyle.State_Off
            chk.rect = box
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
    """Three click targets: ⚑ (Flag), edit (Manual Entry), ✖ (Delete)."""
    editClicked = pyqtSignal(int)    # source row
    deleteClicked = pyqtSignal(int)  # source row

    def __init__(self, parent=None, icon_font: Optional[QFont] = None):
        super().__init__(parent)
        self._icon_font = icon_font
        self._edit_icon = QIcon(_resolve_icon("edit.svg"))

    def _thirds(self, rect: QRect) -> Tuple[QRect, QRect, QRect]:
        w = rect.width()
        h = rect.height()
        pad = max(6, int(h * 0.2))  # more breathing room between actions
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
        flag_font = painter.font()
        flag_font.setPointSize(flag_font.pointSize() + 2)  # bump size up slightly
        painter.setFont(flag_font)
        painter.drawText(left, Qt.AlignCenter, "⚑" if flagged else "⚐")
        # Draw edit (second) using SVG icon, but shrink rect a bit
        edit_rect = mid.adjusted(5, 5, -5, -5)  # add padding on all sides
        self._edit_icon.paint(painter, edit_rect, Qt.AlignCenter)
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
