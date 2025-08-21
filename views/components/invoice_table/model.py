from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Set, Tuple

from PyQt5.QtCore import Qt, QModelIndex, QAbstractTableModel, QVariant, pyqtSignal, QSortFilterProxyModel
from PyQt5.QtGui import QColor

from .utils import (
    to_superscript,
    _parse_date,
    _natural_key,
    _normalize_invoice_number,
)

# =============================================================
# Columns / Headers
# =============================================================
C_SELECT = 0
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

# Body columns used for export/save (no select/actions)
BODY_COLS = range(1, 9)


# =============================================================
# Data Model
# =============================================================
class InvoiceRow:
    __slots__ = ("selected", "flag", "vendor", "invoice", "po", "inv_date", "terms", "due",
                 "disc_total", "total", "file_path", "edited_cells")

    def __init__(self, values: List[str], file_path: str):
        # values: [vendor, invoice, po, inv_date, terms, due, disc_total, total]
        (self.vendor, self.invoice, self.po, self.inv_date, self.terms,
         self.due, self.disc_total, self.total) = (values + [""] * 8)[:8]
        self.file_path = file_path or ""
        self.selected = False         # NEW: user 'Select' checkbox state
        self.flag = False             # kept: flag is now shown inside Actions
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
                return HEADERS[section]
            # Optional: center the select header
            if role == Qt.TextAlignmentRole and section == C_SELECT:
                return Qt.AlignCenter
        return super().headerData(section, orientation, role)

    def flags(self, index: QModelIndex):
        if not index.isValid():
            return Qt.NoItemFlags
        col = index.column()
        base = Qt.ItemIsEnabled | Qt.ItemIsSelectable
        if col == C_SELECT:
            base |= Qt.ItemIsUserCheckable
            return base
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
                vals = self.row_values(r)
                filled = [bool(str(v).strip()) for v in vals]
                all_empty = not any(filled)
                if all_empty:
                    return QColor("#FDE2E2")  # red highlight when entire row is empty
                value = self._get_cell_value(r, c)
                if (value is None) or (str(value).strip() == ""):
                    return QColor("#FFF1A6")  # brighter yellow for empty cell
                if c == C_TERMS:
                    terms = str(value or "")
                    t = terms.strip().lower()
                    if t:
                        has_number = bool(re.search(r"\d", t))
                        has_net = ("net" in t)
                        if (not has_number) and (not has_net):
                            return QColor("#CCE7FF")  # clearer blue for invalid terms
                if c in row.edited_cells:
                    return QColor("#DCFCE7")  # soft green for manually edited
            return QVariant()

        # Checkbox state for the Select column
        if role == Qt.CheckStateRole and c == C_SELECT:
            return Qt.Checked if row.selected else Qt.Unchecked

        # Ensure centered checkbox (no phantom text area)
        if role == Qt.TextAlignmentRole and c == C_SELECT:
            return Qt.AlignCenter

        # Display / Edit content
        if role in (Qt.DisplayRole, Qt.EditRole):
            if c == C_SELECT:
                return ""  # checkbox only
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
                return " ⚑   ✎ ✖ "
        return QVariant()

    def setData(self, index: QModelIndex, value, role=Qt.EditRole):
        if not index.isValid():
            return False
        r, c = index.row(), index.column()
        row = self._rows[r]

        # Toggle checkbox
        if c == C_SELECT and role == Qt.CheckStateRole:
            new_val = (value == Qt.Checked)
            if row.selected != new_val:
                row.selected = new_val
                self.dataChanged.emit(index, index, [Qt.CheckStateRole, Qt.DisplayRole])
            return True

        if role != Qt.EditRole:
            return False

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

        if c == C_INVOICE:
            self._rebuild_duplicates()

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

    # --- flag state (now shown in Actions column) ---
    def get_flag(self, src_row: int) -> bool:
        return self._rows[src_row].flag

    def set_flag(self, src_row: int, val: bool):
        if self._rows[src_row].flag != val:
            self._rows[src_row].flag = val
            idx_actions = self.index(src_row, C_ACTIONS)
            idx_vendor  = self.index(src_row, C_VENDOR)
            # Notify both: Actions (icon) and Vendor (left stripe painter)
            self.dataChanged.emit(idx_actions, idx_actions, [Qt.DisplayRole])
            self.dataChanged.emit(idx_vendor,  idx_vendor,  [Qt.DisplayRole])

    # --- select-all helpers for header checkbox ---
    def set_all_selected(self, checked: bool):
        if not self._rows:
            return
        changed = False
        for i, r in enumerate(self._rows):
            if r.selected != checked:
                r.selected = checked
                changed = True
        if changed:
            top = self.index(0, C_SELECT)
            bottom = self.index(self.rowCount() - 1, C_SELECT)
            self.dataChanged.emit(top, bottom, [Qt.CheckStateRole, Qt.DisplayRole])

    def selection_stats(self) -> Tuple[int, int]:
        total = len(self._rows)
        selected = sum(1 for r in self._rows if r.selected)
        return selected, total
    
    def selected_rows(self) -> List[int]:
        """Return source row indexes with the Select checkbox checked."""
        return [i for i, r in enumerate(self._rows) if r.selected]

    # --- update row by source path ---
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
    def __init__(self, parent=None):
        super().__init__(parent)
        # Search/filter state
        self._text_filter: str = ""
        self._flagged_only: bool = False
        self._incomplete_only: bool = False
        # Track sort state manually so we can disable sorting
        self._sort_column: int = -1
        self._sort_order = Qt.AscendingOrder
        # Search defaults: scan all columns
        self.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.setFilterKeyColumn(-1)

    # ---- Public setters used by the view/window ----
    def set_text_filter(self, text: str):
        self._text_filter = (text or "").strip().casefold()
        self.invalidateFilter()

    def set_flagged_only(self, on: bool):
        self._flagged_only = bool(on)
        self.invalidateFilter()

    def set_incomplete_only(self, on: bool):
        self._incomplete_only = bool(on)
        self.invalidateFilter()

    def is_filtered(self) -> bool:
        return bool(self._text_filter or self._flagged_only or self._incomplete_only)

    # ---- Sorting ----
    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder):
        """Allow column=-1 to restore insertion order."""
        self._sort_column = column
        self._sort_order = order
        super().sort(0 if column < 0 else column, order)

    def _to_float(self, v: object) -> float:
        """Parse numbers robustly for sorting; empty/invalid -> -inf."""
        try:
            s = str(v).strip()
            if not s:
                return float("-inf")
            # Strip currency/commas and keep sign/decimal
            s = s.replace(",", "")
            s = re.sub(r"[^0-9.\-]", "", s)
            if s in ("", "-", "."):
                return float("-inf")
            return float(s)
        except Exception:
            return float("-inf")

    def _safe_natural_key(self, s: object):
        """Normalize natural key parts to comparable tuples."""
        try:
            parts = _natural_key(str(s))
        except Exception:
            parts = [str(s)]
        safe = []
        for p in parts:
            if isinstance(p, (int, float)):
                safe.append((0, float(p)))
            else:
                safe.append((1, str(p).casefold()))
        return tuple(safe)

    def lessThan(self, left: QModelIndex, right: QModelIndex) -> bool:
        if self._sort_column < 0:
            # Default order: preserve source model insertion order
            return left.row() < right.row()

        c = self._sort_column
        src = left.model()  # source model
        l = src.data(src.index(left.row(), c), Qt.EditRole)
        r = src.data(src.index(right.row(), c), Qt.EditRole)

        if c == C_ACTIONS:
            get_flag = getattr(src, "get_flag", None)
            lf = bool(get_flag(left.row())) if get_flag else False
            rf = bool(get_flag(right.row())) if get_flag else False
            if lf != rf:
                return lf and not rf
            lv = src.data(src.index(left.row(), C_VENDOR), Qt.EditRole)
            rv = src.data(src.index(right.row(), C_VENDOR), Qt.EditRole)
            return self._safe_natural_key(lv) < self._safe_natural_key(rv)

        if c in (C_DISC_TOTAL, C_TOTAL):
            lf = self._to_float(l)
            rf = self._to_float(r)
            return lf < rf

        if c in (C_INV_DATE, C_DUE):
            dl = _parse_date(str(l)) or _parse_date("01/01/1900")
            dr = _parse_date(str(r)) or _parse_date("01/01/1900")
            return dl < dr

        return self._safe_natural_key(l) < self._safe_natural_key(r)

    # ---- Filtering ----
    def filterAcceptsRow(self, src_row: int, src_parent) -> bool:
        model = self.sourceModel()
        # 1) Flagged-only (uses data, not a column)
        if self._flagged_only:
            if not getattr(model, "get_flag", None):
                return False
            if not model.get_flag(src_row):
                return False

        # 2) Incomplete-only (any empty body cell)
        vals = model.row_values(src_row)
        if self._incomplete_only:
            if all(bool(str(v).strip()) for v in vals):
                return False

        # 3) Text search
        if self._text_filter:
            hay = " ".join(str(x or "") for x in vals).casefold()
            if self._text_filter not in hay:
                return False

        return True
