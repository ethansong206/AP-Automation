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
C_TOTAL = 7
C_SHIPPING = 8
C_GRAND_TOTAL = 9
C_ACTIONS = 10

HEADERS = [
    "", "Vendor Name", "Invoice Number", "PO Number", "Invoice Date",
    "Discount Terms", "Due Date", "Total", "Shipping",
    "Grand Total", "Actions",
]

# Body columns used for export/save (no select/actions, no grand total)
BODY_COLS = range(1, 9)


# =============================================================
# Data Model
# =============================================================
class InvoiceRow:
    __slots__ = ("selected", "flag", "vendor", "invoice", "po", "inv_date", "terms", "due",
                 "total", "shipping", "grand_total", "file_path", "edited_cells",
                 "qc_subtotal", "qc_disc_pct", "qc_disc_amt", "qc_shipping", "qc_used",
                 "qc_save_state", "qc_original_subtotal", "qc_inventory")

    def __init__(self, values: List[str], file_path: str):
        # values: [vendor, invoice, po, inv_date, terms, due, total, shipping, qc_subtotal, qc_disc_pct, qc_disc_amt, qc_shipping, qc_used, qc_save_state, qc_original_subtotal, qc_inventory]
        extended_values = (values + [""] * 16)[:16]  # Ensure we have all 16 values
        (self.vendor, self.invoice, self.po, self.inv_date, self.terms,
         self.due, self.total, self.shipping, self.qc_subtotal, self.qc_disc_pct,
         self.qc_disc_amt, self.qc_shipping, self.qc_used, self.qc_save_state, 
         self.qc_original_subtotal, self.qc_inventory) = extended_values
        self.file_path = file_path or ""
        self.selected = False         # NEW: user 'Select' checkbox state
        self.flag = False             # kept: flag is now shown inside Actions
        self.edited_cells: Set[int] = set()
        # Grand total is calculated, not stored directly from input
        self._update_grand_total()

    def _update_grand_total(self):
        """Calculate grand total from total and shipping."""
        try:
            total_val = float(str(self.total or "0").replace(",", "").replace("$", "")) if self.total else 0.0
            shipping_val = float(str(self.shipping or "0").replace(",", "").replace("$", "")) if self.shipping else 0.0
            self.grand_total = f"{total_val + shipping_val:.2f}"
        except (ValueError, TypeError):
            self.grand_total = "0.00"


class InvoiceTableModel(QAbstractTableModel):
    # Emitted when an editable body cell changes (source model coordinates)
    rawEdited = pyqtSignal(int, int)  # (row, col)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows: List[InvoiceRow] = []
        # normalized invoice number -> list of source row indexes (duplicates only)
        self._dup_map: Dict[str, List[int]] = {}

    # --- Data access methods ---
    def row_values(self, row: int) -> List[str]:
        """Return all 16 values for a row (8 main + 8 QC values) for session persistence."""
        if row < 0 or row >= len(self._rows):
            return [""] * 16
        
        r = self._rows[row]
        return [
            r.vendor, r.invoice, r.po, r.inv_date, r.terms,
            r.due, r.total, r.shipping, r.qc_subtotal, r.qc_disc_pct,
            r.qc_disc_amt, r.qc_shipping, r.qc_used, r.qc_save_state,
            r.qc_original_subtotal, r.qc_inventory
        ]
    
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
        # Grand Total column is not in BODY_COLS and is not editable
        return base

    # --- data roles ---
    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return QVariant()
        r, c = index.row(), index.column()
        row = self._rows[r]

        # Backgrounds (cell-level)
        if role == Qt.BackgroundRole:
            if c in BODY_COLS or c == C_GRAND_TOTAL:
                vals = self.row_values(r)
                # Exclude shipping (index 7) from empty cell checks
                filled = [bool(str(v).strip()) for i, v in enumerate(vals) if i != 7]
                all_empty = not any(filled)
                if all_empty:
                    return QColor("#FDE2E2")  # red highlight when entire row is empty
                value = self._get_cell_value(r, c)
                # Don't highlight shipping column when empty, and grand total is never editable
                if c not in (C_SHIPPING, C_GRAND_TOTAL) and ((value is None) or (str(value).strip() == "")):
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
                # Grand total gets a light blue background to show it's calculated
                if c == C_GRAND_TOTAL:
                    return QColor("#F0F8FF")  # light blue for calculated field
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
            if c == C_TOTAL:
                return row.total
            if c == C_SHIPPING:
                return row.shipping
            if c == C_GRAND_TOTAL:
                return row.grand_total
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

        old_val = self._get_cell_value(r, c)
        new_val = str(value) if value is not None else ""

        # If the value isn't actually changing, bail out early so we don't
        # mark the cell as edited and highlight it unnecessarily.
        if (old_val or "") == new_val:
            return False

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
            elif c == C_TOTAL:
                row.total = val
                # Recalculate grand total when total changes
                row._update_grand_total()
            elif c == C_SHIPPING:
                row.shipping = val
                # Recalculate grand total when shipping changes
                row._update_grand_total()
            elif c == C_GRAND_TOTAL:
                # Grand total is calculated, not directly editable
                return False
            else:
                return
            row.edited_cells.add(c)

        result = set_and_mark(new_val)
        if result is False:
            return False

        if c == C_INVOICE:
            self._rebuild_duplicates()

        # Emit change for the edited cell
        self.dataChanged.emit(index, index, [Qt.DisplayRole, Qt.EditRole, Qt.BackgroundRole])
        
        # If total or shipping changed, also emit change for grand total column
        if c in (C_TOTAL, C_SHIPPING):
            grand_total_index = self.index(r, C_GRAND_TOTAL)
            self.dataChanged.emit(grand_total_index, grand_total_index, [Qt.DisplayRole])
        
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
            C_TOTAL: r.total,
            C_SHIPPING: r.shipping,
            C_GRAND_TOTAL: r.grand_total,
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
        return [r.vendor, r.invoice, r.po, r.inv_date, r.terms, r.due, r.total, r.shipping,
                r.qc_subtotal, r.qc_disc_pct, r.qc_disc_amt, r.qc_shipping, r.qc_used]

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
                # Update the first 8 visible columns
                for c, val in zip(BODY_COLS, (row_values + [""] * 8)[:8]):
                    self.setData(self.index(i, c), val, Qt.EditRole)
                
                # Update QC values directly on the row object (not visible in table)
                extended_values = (row_values + [""] * 13)[:13]
                r.qc_subtotal = extended_values[8] if len(extended_values) > 8 else ""
                r.qc_disc_pct = extended_values[9] if len(extended_values) > 9 else ""
                r.qc_disc_amt = extended_values[10] if len(extended_values) > 10 else ""
                r.qc_shipping = extended_values[11] if len(extended_values) > 11 else ""
                r.qc_used = extended_values[12] if len(extended_values) > 12 else "false"
                
                print(f"[QC DEBUG] update_row_by_source saved QC values: subtotal={r.qc_subtotal}, disc_pct={r.qc_disc_pct}, disc_amt={r.qc_disc_amt}, shipping={r.qc_shipping}, used={r.qc_used}")
                
                # Recalculate grand total after updating
                r._update_grand_total()
                grand_total_index = self.index(i, C_GRAND_TOTAL)
                self.dataChanged.emit(grand_total_index, grand_total_index, [Qt.DisplayRole])
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

        if c in (C_TOTAL, C_SHIPPING, C_GRAND_TOTAL):
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

        # 2) Incomplete-only (any empty body cell, excluding shipping)
        vals = model.row_values(src_row)
        if self._incomplete_only:
            # Enumerate starting at C_VENDOR so indexes align with column constants
            required = [
                v for i, v in enumerate(vals, start=C_VENDOR)
                if i != C_SHIPPING
            ]
            if all(bool(str(v).strip()) for v in required):
                return False

        # 3) Text search
        if self._text_filter:
            hay = " ".join(str(x or "") for x in vals).casefold()
            if self._text_filter not in hay:
                return False

        return True
