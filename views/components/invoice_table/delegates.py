from __future__ import annotations

from typing import Optional, Tuple

import sys, os
from PyQt5.QtCore import Qt, QModelIndex, QRect, QRectF, QPoint, QSortFilterProxyModel, pyqtSignal, QDate, QTimer
from PyQt5.QtGui import QColor, QFont, QPen, QBrush, QPalette, QPainter, QIcon
from PyQt5.QtWidgets import (
    QStyledItemDelegate, QStyleOptionViewItem, QLineEdit, QStyle, QApplication, QStyleOptionButton
)

from .model import C_VENDOR, C_SELECT, C_INV_DATE, C_DUE
from views.app_shell import _resolve_icon
from PyQt5.QtSvg import QSvgRenderer

# -------------------------------------------------------------
# Utilities
# -------------------------------------------------------------

def resource_path(*parts):
    """Return absolute path, working in dev and in PyInstaller .exe."""
    base = getattr(sys, "_MEIPASS", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))
    return os.path.join(base, *parts)

ASSETS_DIR = resource_path("assets", "icons")


# -------------------------------------------------------------
# Masked date editor for table cells (MM/DD/YY) with dialog parity
# -------------------------------------------------------------

class MaskedDateEditForTable(QLineEdit):
    """
    QLineEdit editor with 'MM/DD/YY' behavior to mirror Manual Entry dialog:
      • Internal buffer so we never fight QLineEdit's cursor quirks
      • First click selects a section; second click places caret
      • Smart digits: impossible first digits auto-pad/advance (MM, DD)
      • '/', Enter, Tab advance; Shift+Tab goes back
      • get_text_value() returns '' when blank/invalid; else 'MM/dd/yy'
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        # Visual mask only; we will manage the text ourselves via _buf
        self.setInputMask("00/00/00;_")
        self.setPlaceholderText("__/__/__")
        self.setStyleSheet("QLineEdit { background:#FFFFFF; color:#000000; border:none; margin:0; padding:0 6px; }")

        # Internal state: text buffer and current segment (0=MM,1=DD,2=YY)
        self._buf = "__/__/__"
        self._seg = 0
        self._last_segment_clicked = None

        self._sync()
        QTimer.singleShot(0, self._select_segment_current)

    # ----- delegate helpers -----
    def set_text_value(self, text_value: str):
        t = (text_value or "").strip()
        if not t:
            self._buf = "__/__/__"
            self._seg = 0
            self._sync()
            QTimer.singleShot(0, self._select_segment_current)
            return
        qd = self._parse_mmddyy(t)
        self._buf = qd.toString("MM/dd/yy") if qd and qd.isValid() else "__/__/__"
        self._seg = 0
        self._sync()
        QTimer.singleShot(0, self._select_segment_current)

    def get_text_value(self) -> str:
        if self._buf == "__/__/__":
            return ""
        return self._buf if self._parse_mmddyy(self._buf) else ""

    # ----- buffer helpers -----
    def _sync(self):
        # Write buffer to widget and keep caret on current segment
        self.setText(self._buf)
        self._select_segment_current()

    @staticmethod
    def _seg_bounds(seg: int):
        return [(0, 2), (3, 5), (6, 8)][seg]

    def _select_segment_current(self):
        s, e = self._seg_bounds(self._seg)
        self.setSelection(s, e - s)
        self.setCursorPosition(s)

    def _segment_text(self, seg: int):
        s, e = self._seg_bounds(seg)
        segtxt = self._buf[s:e]
        if len(segtxt) < 2:
            segtxt = (segtxt + "__")[:2]
        return segtxt[0], segtxt[1]

    def _replace_segment(self, seg: int, two: str):
        two2 = (two or "__")
        two2 = (two2 + "__")[:2]
        s, e = self._seg_bounds(seg)
        self._buf = self._buf[:s] + two2 + self._buf[e:]
        self._sync()

    # ----- finalize helpers -----
    def _finalize_current_segment(self):
        """Pad single-digit month/day when user navigates away (e.g. '3_' -> '03')."""
        a, b = self._segment_text(self._seg)
        if self._seg in (0, 1):
            if a.isdigit() and b == '_':
                self._replace_segment(self._seg, '0' + a)
        # Leave year as-is to avoid surprising auto-fill

    def _finalize_all(self):
        cur = self._seg
        for s in (0, 1):
            self._seg = s
            self._finalize_current_segment()
        self._seg = cur
        self._select_segment_current()

    # ----- events -----
    def focusInEvent(self, e):
        super().focusInEvent(e)
        # Always start at MM when entering
        self._seg = 0
        QTimer.singleShot(0, self._select_segment_current)

    def focusOutEvent(self, e):
        # Before leaving editor, pad single-digit month/day so parse doesn't wipe input
        self._finalize_all()
        super().focusOutEvent(e)

    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return super().mousePressEvent(e)
        # Map x to segment
        cp = self.cursorPositionAt(e.pos())
        seg = 0 if cp <= 2 else (1 if cp <= 5 else 2)
        if self._last_segment_clicked is None or seg != self._last_segment_clicked:
            e.accept()
            # Finalize previous segment before switching
            self._finalize_current_segment()
            self.setFocus(Qt.MouseFocusReason)
            self._seg = seg
            self._select_segment_current()
            self._last_segment_clicked = seg
            return
        # second click in same segment -> allow precise caret
        self._last_segment_clicked = None
        return super().mousePressEvent(e)

    def keyPressEvent(self, e):
        k = e.key()
        t = e.text()

        # '/', Enter, Tab advance; Shift+Tab back
        if k in (Qt.Key_Return, Qt.Key_Enter) or t == '/':
            # finalize current segment before moving on
            self._finalize_current_segment()
            if self._seg < 2:
                self._seg += 1
                self._select_segment_current()
                e.accept(); return
        if k == Qt.Key_Tab:
            self._finalize_current_segment()
            if self._seg < 2:
                self._seg += 1
                self._select_segment_current()
                e.accept(); return
        if k == Qt.Key_Backtab:
            self._finalize_current_segment()
            if self._seg > 0:
                self._seg -= 1
                self._select_segment_current()
                e.accept(); return

        # Smart per-section typing — we fully control the buffer
        if t.isdigit() and len(t) == 1:
            if self._seg == 0:
                self._handle_month_digit(t); e.accept(); return
            if self._seg == 1:
                self._handle_day_digit(t);   e.accept(); return
            if self._seg == 2:
                self._handle_year_digit(t);  e.accept(); return

        # Ignore other editing keys to avoid mask fighting us
        if k in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Delete, Qt.Key_Backspace):
            # Backspace/Delete clears current segment
            if k in (Qt.Key_Backspace, Qt.Key_Delete):
                self._replace_segment(self._seg, "__")
                self._select_segment_current()
                e.accept(); return
        super().keyPressEvent(e)

    def wheelEvent(self, e):
        e.ignore()  # not a spinner

    # ----- smart handlers -----
    def _handle_month_digit(self, d: str):
        a, b = self._segment_text(0)
        # If whole segment selected, treat as empty
        s0, _ = self._seg_bounds(0)
        if self.hasSelectedText() and self.selectionStart() == s0:
            a, b = '_', '_'
        if a == '_' and b == '_':
            if d in '01':
                self._replace_segment(0, d + '_'); self.setCursorPosition(1)
            else:
                self._replace_segment(0, '0' + d); self._seg = 1; self._select_segment_current()
            return
        first = a if a != '_' else '0'
        if first == '0':
            if d == '0':
                return  # disallow 00
            self._replace_segment(0, first + d); self._seg = 1; self._select_segment_current(); return
        if first == '1' and d in '012':
            self._replace_segment(0, first + d); self._seg = 1; self._select_segment_current()

    def _handle_day_digit(self, d: str):
        a, b = self._segment_text(1)
        s1, _ = self._seg_bounds(1)
        if self.hasSelectedText() and self.selectionStart() == s1:
            a, b = '_', '_'
        if a == '_' and b == '_':
            if d in '012':
                self._replace_segment(1, d + '_'); self.setCursorPosition(4)
            elif d == '3':
                # allow 30/31 if user types second digit; if they navigate away, we'll pad to 03
                self._replace_segment(1, '3_'); self.setCursorPosition(4)
            else:
                self._replace_segment(1, '0' + d); self._seg = 2; self._select_segment_current()
            return
        first = a if a != '_' else '0'
        if first == '0':
            if d == '0': return
            self._replace_segment(1, first + d); self._seg = 2; self._select_segment_current(); return
        if first in '12':
            self._replace_segment(1, first + d); self._seg = 2; self._select_segment_current(); return
        if first == '3' and d in '01':
            self._replace_segment(1, '3' + d); self._seg = 2; self._select_segment_current()

    def _handle_year_digit(self, d: str):
        a, b = self._segment_text(2)
        s2, _ = self._seg_bounds(2)
        if self.hasSelectedText() and self.selectionStart() == s2:
            a, b = '_', '_'
        if a == '_' and b == '_':
            self._replace_segment(2, d + '_'); self.setCursorPosition(7); return
        if a != '_' and b == '_':
            self._replace_segment(2, a + d); self.setCursorPosition(8); return
        # both digits present → keep caret at end of YY
        self.setCursorPosition(8)

    # ----- parsing -----
    def _parse_mmddyy(self, s: str):
        parts = (s or "").split("/")
        if len(parts) != 3:
            return None
        try:
            m, d, y = int(parts[0]), int(parts[1]), int(parts[2])
        except ValueError:
            return None
        if not (1 <= m <= 12 and 1 <= d <= 31):
            return None
        if y < 100:
            y = 2000 + y
        qd = QDate(y, m, d)
        return qd if qd.isValid() else None


# -------------------------------------------------------------
# Body delegate
# -------------------------------------------------------------

class BodyEditDelegate(QStyledItemDelegate):
    def createEditor(self, parent, option, index):
        # Use the masked date editor for date columns only
        if index.column() in (C_INV_DATE, C_DUE):
            ed = MaskedDateEditForTable(parent)
            ed.setAutoFillBackground(True)
            ed.returnPressed.connect(lambda: self.commitData.emit(ed))  # commit on Enter
            return ed

        # Non-date: simple line edit with padding to match look
        editor = QLineEdit(parent)
        editor.setAutoFillBackground(True)
        editor.setStyleSheet("background:#FFFFFF; color:#000000; padding:0 6px; margin:0;")
        return editor

    def setEditorData(self, editor, index):
        # Use EditRole so we don't accidentally pick up display formatting
        if isinstance(editor, MaskedDateEditForTable):
            editor.set_text_value(str(index.data(Qt.EditRole) or ""))
            return
        editor.setText(str(index.data(Qt.EditRole) or ""))

    def setModelData(self, editor, model, index):
        if isinstance(editor, MaskedDateEditForTable):
            model.setData(index, editor.get_text_value(), Qt.EditRole)
            return
        model.setData(index, editor.text(), Qt.EditRole)

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index: QModelIndex):
        opt = QStyleOptionViewItem(option)
        if opt.state & QStyle.State_Editing:
            painter.save()
            painter.fillRect(opt.rect, opt.palette.base())
            painter.restore()
            return

        self.initStyleOption(opt, index)

        # Honor BackgroundRole brush if present
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

        # Nudge text right for breathing room
        opt.rect.adjust(6, 0, 0, 0)

        # Show placeholder for empty date cells
        if index.column() in (C_INV_DATE, C_DUE):
            text_value = str(index.data(Qt.DisplayRole) or "")
            if not text_value.strip():
                painter.save()
                painter.setPen(QPen(QColor("#999999")))
                painter.drawText(opt.rect, opt.displayAlignment, "__/__/__")
                painter.restore()
                return

        # Default paint
        QStyledItemDelegate.paint(self, painter, opt, index)

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


# -------------------------------------------------------------
# Checkbox delegate (centered SVG checkbox)
# -------------------------------------------------------------

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


# -------------------------------------------------------------
# Actions delegate (flag, edit, delete)
# -------------------------------------------------------------

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
