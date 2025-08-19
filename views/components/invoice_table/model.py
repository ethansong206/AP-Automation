from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Set

from PyQt5.QtCore import Qt, QModelIndex, QAbstractTableModel, QVariant, pyqtSignal, QSortFilterProxyModel
from PyQt5.QtGui import QColor

from .utils import (
    to_superscript,
    _parse_date,
    _parse_money,
    _natural_key,
    _normalize_invoice_number,
)

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
    "Actions",
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