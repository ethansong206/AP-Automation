from __future__ import annotations

import os
import re
from datetime import datetime
from typing import List, Dict, Tuple, Optional, Set

from PyQt5.QtCore import (
    Qt, QModelIndex, QAbstractTableModel, QVariant, pyqtSignal, QRect, QRectF, QPoint,
    QSortFilterProxyModel
)
from PyQt5.QtGui import (
    QColor, QFont, QFontMetrics, QPainter, QPen, QPainterPath, QRegion, QPalette, QBrush
)
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QFrame, QTableView,
    QStyledItemDelegate, QStyleOptionViewItem, QMessageBox, QHeaderView, QAbstractItemView,
    QLineEdit, QStyle
)

# =============================================================
# Helpers
# =============================================================
_SUPERSCRIPT_TRANS = str.maketrans("0123456789", "⁰¹²³⁴⁵⁶⁷⁸⁹")


def to_superscript(n: int) -> str:
    return str(n).translate(_SUPERSCRIPT_TRANS)


def _parse_date(text: str) -> Optional[datetime]:
    text = (text or "").strip()
    if not text:
        return None
    fmts = ["%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%d", "%m/%d/%y"]
    for f in fmts:
        try:
            return datetime.strptime(text, f)
        except ValueError:
            pass
    return None


def _parse_money(text: str) -> Optional[float]:
    if text is None:
        return None
    s = re.sub(r"[^\d\.\-]", "", str(text))
    if s in {"", "-", ".", "-.", ".-"}:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _natural_key(s: str) -> Tuple:
    """Case-insensitive natural sort key."""
    return tuple(int(t) if t.isdigit() else t.lower() for t in re.findall(r'\d+|\D+', s or ""))


def _normalize_invoice_number(s: str) -> str:
    return re.sub(r'[^a-z0-9]', '', (s or "").lower())


# =============================================================
# Columns / Headers
# =============================================================
C_FLAG = 0
C_VENDOR = 1
C_INVOICE = 2
C_PO = 3
C_INV_DATE = 4
C_TERMS = 5
C_DUE = 6
C_DISC_TOTAL = 7
C_TOTAL = 8
C_ACTIONS = 9

HEADERS = [
    "", "Vendor Name", "Invoice Number", "PO Number", "Invoice Date",
    "Discount Terms", "Due Date", "Discounted Total", "Total Amount",
    "Actions"
]

# Body columns used for export/save (no flag/actions)
BODY_COLS = range(1, 9)


# =============================================================
# Data Model
# =============================================================
class InvoiceRow:
    __slots__ = ("flag", "vendor", "invoice", "po", "inv_date", "terms", "due",
                 "disc_total", "total", "file_path", "edited_cells")

    def __init__(self, values: List[str], file_path: str):
        # values: [vendor, invoice, po, inv_date, terms, due, disc_total, total]
        (self.vendor, self.invoice, self.po, self.inv_date, self.terms,
         self.due, self.disc_total, self.total) = (values + [""] * 8)[:8]
        self.file_path = file_path or ""
        self.flag = False
        self.edited_cells: Set[int] = set()


class InvoiceTableModel(QAbstractTableModel):
    # Emitted when an editable body cell changes (source model coordinates)
    rawEdited = pyqtSignal(int, int)  # (row, col)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: List[InvoiceRow] = []
        # normalized invoice number -> list of source row indexes (duplicates only)
        self._dup_map: Dict[str, List[int]] = {}

    # --- Qt plumbing ---
    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent=QModelIndex()) -> int:
        return len(HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if orientation == Qt.Horizontal:
            if role == Qt.DisplayRole:
                # Show a flag icon glyph in the header for the flag column
                if section == C_FLAG:
                    return "⚑"
                return HEADERS[section]
            if role == Qt.TextAlignmentRole:
                # Center the glyph in the flag header
                if section == C_FLAG:
                    return Qt.AlignCenter
            if role == Qt.ToolTipRole and section == C_FLAG:
                return "Flag"
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        col = index.column()
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if col in BODY_COLS:
            base |= Qt.ItemIsEditable
        return base

    # --- data roles ---
    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        r, c = index.row(), index.column()
        row = self._rows[r]

        # Backgrounds (cell-level)
        if role == Qt.BackgroundRole:
            if c in BODY_COLS:
                # Row-level emptiness to drive red full-row highlight
                vals = self.row_values(r)
                filled = [bool(str(v).strip()) for v in vals]
                all_empty = not any(filled)
                if all_empty:
                    return QColor("#FDE2E2")  # red highlight when entire row is empty
                # Cell-level states
                value = self._get_cell_value(r, c)
                if (value is None) or (str(value).strip() == ""):
                    return QColor("#FFF1A6")  # brighter yellow for empty cell
                # Discount Terms validation: highlight blue only if it has NEITHER 'NET' nor any number
                if c == C_TERMS:
                    terms = str(value or "")
                    t = terms.strip().lower()
                    if t:
                        has_number = bool(re.search(r"\d", t))
                        has_net = ("net" in t)
                        if (not has_number) and (not has_net):
                            return QColor("#CCE7FF")  # clearer blue for invalid terms
                # Manually edited fallback highlight
                if c in row.edited_cells:
                    return QColor("#DCFCE7")  # soft green for manually edited
            return QVariant()

        # Display content
        if role in (Qt.DisplayRole, Qt.EditRole):
            if c == C_FLAG:
                return "⚑" if row.flag else "⚐"  # visual; delegate handles click
            if c == C_VENDOR:
                return row.vendor
            if c == C_INVOICE:
                base = row.invoice or ""
                sup = self._duplicate_number_for_row(r)
                return f"{base}{to_superscript(sup)}" if sup else base
            if c == C_PO:
                return row.po
            if c == C_INV_DATE:
                return row.inv_date
            if c == C_TERMS:
                return row.terms
            if c == C_DUE:
                return row.due
            if c == C_DISC_TOTAL:
                return row.disc_total
            if c == C_TOTAL:
                return row.total
            if c == C_ACTIONS:
                return "✎  ✖"  # placeholder text; delegate paints icons
        return QVariant()

    def setData(self, index: QModelIndex, value, role=Qt.EditRole):
        if role != Qt.EditRole or not index.isValid():
            return False
        r, c = index.row(), index.column()
        row = self._rows[r]
        old = self._get_cell_value(r, c)

        def set_and_mark(val):
            if c == C_VENDOR:
                row.vendor = val
            elif c == C_INVOICE:
                row.invoice = val
            elif c == C_PO:
                row.po = val
            elif c == C_INV_DATE:
                row.inv_date = val
            elif c == C_TERMS:
                row.terms = val
            elif c == C_DUE:
                row.due = val
            elif c == C_DISC_TOTAL:
                row.disc_total = val
            elif c == C_TOTAL:
                row.total = val
            else:
                return
            row.edited_cells.add(c)

        set_and_mark(str(value) if value is not None else "")

        # Recompute duplicates if invoice number changed
        if c == C_INVOICE:
            self._rebuild_duplicates()

        # (Due Date recompute removed; controller handles it)
        if old != value:
            self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole, Qt.BackgroundRole])
            self.rawEdited.emit(r, c)
        return True

    # --- helpers ---
    def _get_cell_value(self, row: int, col: int) -> Optional[str]:
        r = self._rows[row]
        return {
            C_VENDOR: r.vendor,
            C_INVOICE: r.invoice,
            C_PO: r.po,
            C_INV_DATE: r.inv_date,
            C_TERMS: r.terms,
            C_DUE: r.due,
            C_DISC_TOTAL: r.disc_total,
            C_TOTAL: r.total,
        }.get(col, "")

    def _duplicate_number_for_row(self, r: int) -> int:
        inv = _normalize_invoice_number(self._rows[r].invoice)
        if not inv:
            return 0
        group = self._dup_map.get(inv, [])
        if len(group) <= 1:
            return 0
        try:
            return group.index(r) + 1  # 1-based within dup group
        except ValueError:
            return 0

    def _rebuild_duplicates(self):
        d: Dict[str, List[int]] = {}
        for i, row in enumerate(self._rows):
            key = _normalize_invoice_number(row.invoice)
            if not key:
                continue
            d.setdefault(key, []).append(i)
        self._dup_map = {k: v for k, v in d.items() if len(v) > 1}
        if self._rows:
            top = self.index(0, C_INVOICE)
            bottom = self.index(self.rowCount() - 1, C_INVOICE)
            self.dataChanged.emit(top, bottom, [Qt.DisplayRole])

    # --- mutations used by view wrapper ---
    def add_row(self, values: List[str], file_path: str):
        self.beginInsertRows(QModelIndex(), len(self._rows), len(self._rows))
        self._rows.append(InvoiceRow(values, file_path))
        self.endInsertRows()
        self._rebuild_duplicates()

    def remove_row(self, src_row: int):
        if 0 <= src_row < len(self._rows):
            self.beginRemoveRows(QModelIndex(), src_row, src_row)
            del self._rows[src_row]
            self.endRemoveRows()
            self._rebuild_duplicates()

    def clear(self):
        if not self._rows:
            return
        self.beginRemoveRows(QModelIndex(), 0, len(self._rows) - 1)
        self._rows.clear()
        self.endRemoveRows()
        self._dup_map.clear()

    def row_values(self, src_row: int) -> List[str]:
        r = self._rows[src_row]
        return [r.vendor, r.invoice, r.po, r.inv_date, r.terms, r.due, r.disc_total, r.total]

    def get_file_path(self, src_row: int) -> str:
        return self._rows[src_row].file_path

    def set_file_path(self, src_row: int, path: str):
        self._rows[src_row].file_path = path or ""

    def get_flag(self, src_row: int) -> bool:
        return self._rows[src_row].flag

    def set_flag(self, src_row: int, val: bool):
        if self._rows[src_row].flag != val:
            self._rows[src_row].flag = val
            idx = self.index(src_row, C_FLAG)
            self.dataChanged.emit(idx, idx, [Qt.DisplayRole])

    def update_row_by_source(self, file_path: str, row_values: List[str]) -> int:
        """Return src row index or -1 if not found."""
        abs_target = os.path.abspath(file_path or "")
        for i, r in enumerate(self._rows):
            if os.path.abspath(r.file_path or "") == abs_target:
                for c, val in zip(BODY_COLS, (row_values + [""] * 8)[:8]):
                    self.setData(self.index(i, c), val, Qt.EditRole)
                return i
        return -1


# =============================================================
# Sorting Proxy
# =============================================================
class InvoiceSortProxy(QSortFilterProxyModel):
    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        c = left.column()
        l = left.model().data(left, Qt.EditRole)
        r = right.model().data(right, Qt.EditRole)

        if c == C_FLAG:
            return (l == "⚑") and (r != "⚑")  # flagged first on that column

        if c in (C_VENDOR, C_TERMS):
            return (l or "").lower() < (r or "").lower()

        if c in (C_INVOICE, C_PO):
            return _natural_key(l or "") < _natural_key(r or "")

        if c in (C_INV_DATE, C_DUE):
            ld, rd = _parse_date(l or ""), _parse_date(r or "")
            if ld and rd:
                return ld < rd
            if ld and not rd:
                return True
            if rd and not ld:
                return False
            return (l or "") < (r or "")

        if c in (C_DISC_TOTAL, C_TOTAL):
            lf, rf = _parse_money(l), _parse_money(r)
            if lf is None and rf is None:
                return (l or "") < (r or "")
            if lf is None:
                return False
            if rf is None:
                return True
            return lf < rf

        return (l or "") < (r or "")


# =============================================================
# Delegates (Stripe, Flag, Actions)

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


# =============================================================
# Rounded clipper to hard-cut the table to rounded corners
# =============================================================
class RoundedClipper(QFrame):
    """Child frame that clips its contents to a rounded rect so children
    (the table) don't bleed under the parent's rounded corners."""
    def __init__(self, radius: int = 17, parent=None):
        super().__init__(parent)
        self._radius = radius
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setContentsMargins(0, 0, 0, 0)
        self.setObjectName("RoundedClipper")

    def setRadius(self, r: int):
        self._radius = r
        self._updateMask()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._updateMask()

    def _updateMask(self):
        rect = self.rect()
        if rect.isEmpty():
            return
        path = QPainterPath()
        # Use QRectF + float radii to satisfy overload
        path.addRoundedRect(QRectF(rect), float(self._radius), float(self._radius))
        region = QRegion(path.toFillPolygon().toPolygon())
        self.setMask(region)


# =============================================================
# Public View Wrapper (compat API)
# =============================================================
class InvoiceTable(QWidget):
    """
    Public-facing widget that:
      - exposes the same API/signals as the former QTableWidget version,
      - renders a QTableView inside a rounded, bordered mini-card,
      - wires model + proxy + delegates.
    """
    # Signals preserved for controller wiring
    row_deleted = pyqtSignal(int, str)              # (view_row, file_path)
    source_file_clicked = pyqtSignal(str)           # file_path
    manual_entry_clicked = pyqtSignal(int, object)  # (view_row, button=None)
    cell_manually_edited = pyqtSignal(int, int)     # (view_row, view_col)
    cellChanged = pyqtSignal(int, int)              # mirror QTableWidget cellChanged

    def __init__(self, parent=None):
        super().__init__(parent)

        # --- Outer mini-card container ---
        self._card = QFrame(self)
        self._card.setObjectName("TableCard")
        self._card.setFrameShape(QFrame.NoFrame)
        self._card.setGraphicsEffect(None)  # no shadow per latest design

        # QTableView itself
        self.table = QTableView(self._card)
        self.table.setObjectName("InvoiceQTableView")
        
        # Increase body (data) font by ~+4pt
        body_font = self.table.font()
        if body_font.pointSizeF() > 0:
            body_font.setPointSizeF(body_font.pointSizeF() + 4.0)
        else:
            body_font.setPixelSize(max(body_font.pixelSize() + 6, 14))
        self.table.setFont(body_font)
        metrics = self.table.fontMetrics()
        row_h = max(32, metrics.height() + 12)

        # Icon font ~25% larger than body (used for flag + action glyphs)
        self._icon_font = QFont(body_font)
        if self._icon_font.pointSizeF() > 0:
            self._icon_font.setPointSizeF(self._icon_font.pointSizeF() * 1.25)
        else:
            self._icon_font.setPixelSize(int(max(int(body_font.pixelSize() * 1.25), body_font.pixelSize() + 3)))

        icon_metrics = QFontMetrics(self._icon_font)
        row_h = max(row_h, icon_metrics.height() + 12)
        self.table.verticalHeader().setDefaultSectionSize(row_h)

        # Layout: main → card → clipper → table
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._card)

        card_layout = QVBoxLayout(self._card)
        card_layout.setContentsMargins(0, 0, 0, 0)

        # Clipper ensures the table is hard-clipped to rounded corners
        self._clipper = RoundedClipper(radius=17, parent=self._card)
        self._clipper.setStyleSheet("background: transparent;")
        card_layout.addWidget(self._clipper)

        inner = QVBoxLayout(self._clipper)
        inner.setContentsMargins(0, 0, 0, 0)
        inner.addWidget(self.table)
        self.table.setViewportMargins(0, 0, 0, 0)

        # Styling
        self.setStyleSheet(
            """
            QFrame#TableCard {
                background: #FFFFFF;
                border: 2px solid #C4CAD3;   /* thicker, slightly darker gray border */
                border-radius: 16px;
            }
            QFrame#RoundedClipper { background: transparent; }

            QTableView#InvoiceQTableView {
                background: transparent;        /* shows white below */
                border: none;
                gridline-color: #EEF1F4;
                selection-background-color: #E6F2FF;
                selection-color: #000000;
                /* alternate row color handled via palette AlternateBase */
            }
            QTableView#InvoiceQTableView::item { border: none; }
            
            /* Ensure editors are opaque so typed text doesn't overlap with painted text */
            QTableView#InvoiceQTableView QLineEdit,
            QTableView#InvoiceQTableView QTextEdit,
            QTableView#InvoiceQTableView QPlainTextEdit {
                background: #FFFFFF;
                color: #000000;
                padding: 0 4px;
            }

            QHeaderView::section {
                background: #FFFFFF;            /* white header */
                padding: 6px;
                border: none;
                border-bottom: 1px solid #E0E4EA; /* divider */
            }
            QTableCornerButton::section {
                background: #FFFFFF;
                border: none;
                border-bottom: 1px solid #E0E4EA;
                border-right: 1px solid #E0E4EA;
            }
            """
        )

        # Model + Proxy
        self._model = InvoiceTableModel(self)
        self._proxy = InvoiceSortProxy(self)
        self._proxy.setSourceModel(self._model)
        self.table.setModel(self._proxy)

        # Zebra rows via palette so model BackgroundRole (e.g., yellow empties) still wins
        pal = self.table.palette()
        pal.setColor(QPalette.AlternateBase, QColor("#F1F4F8"))  # slightly darker than before
        self.table.setPalette(pal)

        # View behavior
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        self.table.setFrameShape(QFrame.NoFrame)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(QTableView.SelectItems)
        self.table.setSelectionMode(QTableView.ExtendedSelection)
        self.table.setEditTriggers(QAbstractItemView.DoubleClicked | QAbstractItemView.SelectedClicked | QAbstractItemView.EditKeyPressed)
        self.table.verticalHeader().setVisible(False)   # hide row numbers
        self.table.setCornerButtonEnabled(False)        # hide corner button
        self.table.setMouseTracking(True)

        # Compatibility with legacy controller code
        self.manually_edited = set()

        # Columns: stretch body to fill; keep flag/actions compact
        header = self.table.horizontalHeader()
        header.setDefaultSectionSize(120)
        header.setMinimumSectionSize(24)
        for c in BODY_COLS:
            header.setSectionResizeMode(c, QHeaderView.Stretch)
        # Make flag column square: fix width to current row height and keep in sync
        header.setSectionResizeMode(C_FLAG, QHeaderView.Fixed)
        header.resizeSection(C_FLAG, row_h)
        self.table.verticalHeader().sectionResized.connect(self._on_row_height_changed)
        # Actions auto-size
        header.setSectionResizeMode(C_ACTIONS, QHeaderView.ResizeToContents)

        # Delegates
  # base stripe for all cells

        self._flag_delegate = FlagDelegate(self.table, self._icon_font)
        self.table.setItemDelegateForColumn(C_FLAG, self._flag_delegate)

        self._actions_delegate = ActionsDelegate(self.table, self._icon_font)
        self.table.setItemDelegateForColumn(C_ACTIONS, self._actions_delegate)
        self._actions_delegate.editClicked.connect(self._emit_manual_entry)
        self._actions_delegate.deleteClicked.connect(self._handle_delete_clicked)

        # Body editor delegate: opaque editors + no underlying paint while editing
        self._body_delegate = BodyEditDelegate(self.table)
        for c in BODY_COLS:
            self.table.setItemDelegateForColumn(c, self._body_delegate)

        # Edits → compatibility signals
        self._model.rawEdited.connect(self._bubble_edit_signal)

    # ---------------------------------------------------------
    # Signal bubbling / helpers
    # ---------------------------------------------------------
    def _on_row_height_changed(self, logical_index: int, old_size: int, new_size: int):
        # Keep the flag column square by matching its width to the row height
        self.table.horizontalHeader().resizeSection(C_FLAG, new_size)

    
    def _bubble_edit_signal(self, src_row: int, src_col: int):
        view_row = self._source_to_view_row(src_row)
        view_col = src_col
        self.cell_manually_edited.emit(view_row, view_col)
        self.cellChanged.emit(view_row, view_col)

    def _emit_manual_entry(self, src_row: int):
        # placeholder for button param to keep signature
        self.manual_entry_clicked.emit(self._source_to_view_row(src_row), None)

    def _handle_delete_clicked(self, src_row: int):
        file_path = self._model.get_file_path(src_row)
        confirm = QMessageBox.question(
            self, "Delete Row", "Are you sure you want to delete this row?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            view_row = self._source_to_view_row(src_row)
            self._model.remove_row(src_row)
            self.row_deleted.emit(view_row, file_path)

    def _open_source_file(self, vrow: int):
        src_row = self._view_to_source_row(vrow)
        if src_row < 0:
            return
        path = self._model.get_file_path(src_row)
        if path:
            self.source_file_clicked.emit(path)

    def update_calculated_field(self, view_row: int, col: int, value: str, force: bool = True):
        """Compatibility method used by the legacy controller:
        write a computed value into the model at (row, col)."""
        src = self._view_to_source_row(view_row)
        if src < 0:
            return
        idx = self._model.index(src, col)
        self._model.setData(idx, value, Qt.EditRole)

    # ---------------------------------------------------------
    # Public API (compat with your existing code)
    # ---------------------------------------------------------
    def add_row(self, row_data: List[str], file_path: str, is_no_ocr: bool = False):
        """row_data = [vendor, invoice, po, inv_date, terms, due, disc_total, total]"""
        self._model.add_row(row_data, file_path)

    def update_row_by_source(self, file_path: str, row_values: List[str]):
        self._model.update_row_by_source(file_path, row_values)

    def get_file_path_for_row(self, view_row: int) -> str:
        src = self._view_to_source_row(view_row)
        return "" if src < 0 else self._model.get_file_path(src)

    def get_cell_text(self, view_row: int, col: int) -> str:
        src = self._view_to_source_row(view_row)
        if src < 0:
            return ""
        # Return RAW (no superscript) for export/save
        vals = self._model.row_values(src)
        mapping = {
            C_VENDOR: 0, C_INVOICE: 1, C_PO: 2, C_INV_DATE: 3,
            C_TERMS: 4, C_DUE: 5, C_DISC_TOTAL: 6, C_TOTAL: 7
        }
        if col in mapping:
            return vals[mapping[col]] or ""
        return ""

    def is_row_flagged(self, view_row: int) -> bool:
        src = self._view_to_source_row(view_row)
        return False if src < 0 else self._model.get_flag(src)

    def toggle_row_flag(self, view_row: int):
        src = self._view_to_source_row(view_row)
        if src >= 0:
            self._model.set_flag(src, not self._model.get_flag(src))

    def find_row_by_file_path(self, file_path: str) -> int:
        abs_target = os.path.abspath(file_path or "")
        for i in range(self._model.rowCount()):
            if os.path.abspath(self._model.get_file_path(i) or "") == abs_target:
                return self._source_to_view_row(i)
        return -1

    def delete_row_by_file_path(self, file_path: str, confirm: bool = False) -> bool:
        abs_target = os.path.abspath(file_path or "")
        for i in range(self._model.rowCount()):
            if os.path.abspath(self._model.get_file_path(i) or "") == abs_target:
                if confirm:
                    ans = QMessageBox.question(
                        self, "Delete Row", "Are you sure you want to delete this row?",
                        QMessageBox.Yes | QMessageBox.No
                    )
                    if ans != QMessageBox.Yes:
                        return False
                view_row = self._source_to_view_row(i)
                self._model.remove_row(i)
                self.row_deleted.emit(view_row, file_path)
                return True
        return False

    def clear_tracking_data(self):
        for i in range(self._model.rowCount()):
            self._model._rows[i].edited_cells.clear()
        self._model._rebuild_duplicates()

    def cleanup_row_data(self, row: int):
        # compatibility no-op; keep for callers that expect it
        pass

    # Qt-style helpers mirrored
    def rowCount(self) -> int:
        return self._proxy.rowCount()

    def setRowCount(self, n: int):
        if n == 0:
            self._model.clear()

    def removeRow(self, view_row: int):
        src = self._view_to_source_row(view_row)
        if src >= 0:
            self._model.remove_row(src)

    def selectedIndexes(self):
        return self.table.selectedIndexes()

    # Mapping helpers
    def _view_to_source_row(self, vrow: int) -> int:
        if vrow < 0 or vrow >= self._proxy.rowCount():
            return -1
        src = self._proxy.mapToSource(self._proxy.index(vrow, 0))
        return src.row()

    def _source_to_view_row(self, srow: int) -> int:
        if srow < 0 or srow >= self._model.rowCount():
            return -1
        v = self._proxy.mapFromSource(self._model.index(srow, 0))
        return v.row()
