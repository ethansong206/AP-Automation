import os
import csv
import re

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QTableView, QPushButton,
    QHBoxLayout, QMessageBox, QLineEdit, QHeaderView
)
from PyQt5.QtCore import Qt, QSortFilterProxyModel, pyqtSignal, QTimer
from PyQt5.QtGui import QColor, QStandardItemModel, QStandardItem

from utils import get_vendor_csv_path
from views.components.invoice_table.utils import _natural_key


class VendorSortProxy(QSortFilterProxyModel):
    """Sorting proxy for vendor table with natural sorting and vendor number validation."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._sort_column = -1  # Default: no sort (alphabetical by vendor name)
        self._sort_order = Qt.AscendingOrder
    
    def sort(self, column: int, order: Qt.SortOrder = Qt.AscendingOrder):
        """Allow column=-1 to restore default alphabetical order by vendor name."""
        self._sort_column = column
        self._sort_order = order
        if column < 0:
            # Default sort: alphabetical by vendor name (column 0)
            super().sort(0, Qt.AscendingOrder)
        else:
            super().sort(column, order)
    
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
    
    def _normalize_vendor_number(self, s: str) -> str:
        """Extract and normalize vendor number for sorting."""
        digits = "".join(ch for ch in (s or "") if ch.isdigit())
        return digits.zfill(7) if digits else ""
    
    def lessThan(self, left, right):
        if self._sort_column < 0:
            # Default order: alphabetical by vendor name
            left_item = self.sourceModel().item(left.row(), 0)
            right_item = self.sourceModel().item(right.row(), 0)
            left_data = left_item.text() if left_item else ""
            right_data = right_item.text() if right_item else ""
            return self._safe_natural_key(left_data) < self._safe_natural_key(right_data)
        
        left_data = left.data(Qt.DisplayRole) or ""
        right_data = right.data(Qt.DisplayRole) or ""
        
        # Column 1 is vendor numbers - normalize for proper sorting
        if self._sort_column == 1:
            left_norm = self._normalize_vendor_number(str(left_data))
            right_norm = self._normalize_vendor_number(str(right_data))
            return left_norm < right_norm
        
        # All other columns use natural key sorting
        return self._safe_natural_key(str(left_data)) < self._safe_natural_key(str(right_data))


class VendorTableHeader(QHeaderView):
    """Custom header that implements the same sorting logic as invoice table."""
    
    def __init__(self, orientation, parent=None):
        super().__init__(orientation, parent)
        self.setSectionsClickable(True)
        self.setHighlightSections(False)
        # Enable column resizing
        self.setSectionResizeMode(QHeaderView.Interactive)
        self.setStretchLastSection(True)
    
    def mousePressEvent(self, event):
        if event.button() != Qt.LeftButton:
            super().mousePressEvent(event)
            return
        
        # Check if we're near a section border (for resizing)
        idx = self.logicalIndexAt(event.pos())
        if idx >= 0:
            # Get the visual position of the section
            section_pos = self.sectionViewportPosition(idx)
            section_size = self.sectionSize(idx)
            
            # Check if we're within 5 pixels of either edge
            pos_x = event.pos().x()
            near_left_edge = abs(pos_x - section_pos) <= 5 and idx > 0
            near_right_edge = abs(pos_x - (section_pos + section_size)) <= 5
            
            # If near an edge, let the default behavior handle resizing
            if near_left_edge or near_right_edge:
                super().mousePressEvent(event)
                return
        
        # Not near an edge, handle sorting
        if idx < 0:
            super().mousePressEvent(event)
            return
            
        view = self.parent()
        proxy = view.model()
        
        # Manual sort cycling: desc → asc → default (alphabetical by vendor name)
        prev_col = getattr(proxy, "_sort_column", -1)
        prev_order = getattr(proxy, "_sort_order", Qt.AscendingOrder)
        
        if prev_col != idx:
            # First click: descending
            next_col, next_order, show_indicator = idx, Qt.DescendingOrder, True
        elif prev_order == Qt.DescendingOrder:
            # Second click: ascending
            next_col, next_order, show_indicator = idx, Qt.AscendingOrder, True
        elif prev_order == Qt.AscendingOrder:
            # Third click: default (alphabetical by vendor name)
            next_col, next_order, show_indicator = -1, Qt.AscendingOrder, False
        else:
            # Fallback: descending
            next_col, next_order, show_indicator = idx, Qt.DescendingOrder, True
        
        view.sortByColumn(next_col, next_order)
        if show_indicator:
            self.setSortIndicatorShown(True)
            self.setSortIndicator(next_col, next_order)
        else:
            self.setSortIndicatorShown(False)


class VendorListDialog(QDialog):
    """Editable vendor list with integrated identifier support in single CSV."""
    
    # Signal emitted when vendor list is successfully saved
    vendor_list_updated = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vendor List")
        self.resize(700, 500)

        # Model/View setup
        self.model = QStandardItemModel(0, 3, self)
        self.model.setHorizontalHeaderLabels([
            "Vendor Name", "Vendor Number", "Vendor Identifier"
        ])
        
        self.proxy = VendorSortProxy(self)
        self.proxy.setSourceModel(self.model)
        
        self.table = QTableView(self)
        self.table.setModel(self.proxy)
        
        # Custom sortable header
        header = VendorTableHeader(Qt.Horizontal, self.table)
        self.table.setHorizontalHeader(header)
        
        # Enable table interactions
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(True)
        
        # Default sorting: alphabetical by vendor name, no indicator
        self.table.sortByColumn(-1, Qt.AscendingOrder)
        header.setSortIndicatorShown(False)
        
        # Connect model changes
        self.model.itemChanged.connect(self._handle_item_changed)
        
        # Connect proxy model signals to ensure view updates
        self.proxy.modelReset.connect(self.table.reset)
        self.proxy.layoutChanged.connect(self.table.update)

        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("Search vendors…")
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setObjectName("searchEdit")
        self.search_edit.textChanged.connect(self._apply_filter)

        btn_layout = QHBoxLayout()
        self.add_row_btn = QPushButton("Add Row")
        self.delete_row_btn = QPushButton("Delete Row")
        self.save_btn = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")
        self.add_row_btn.clicked.connect(self.add_row)
        self.delete_row_btn.clicked.connect(self.delete_row)
        self.save_btn.clicked.connect(self._save_and_close)
        self.cancel_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.add_row_btn)
        btn_layout.addWidget(self.delete_row_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.search_edit)
        layout.addWidget(self.table)
        layout.addLayout(btn_layout)

        self._dirty = False
        self.original = {}
        self._validation_timer = None
        
        # Load data after everything is set up
        self._load_data()
        
    def showEvent(self, event):
        """Override showEvent to set column widths after dialog is properly sized."""
        super().showEvent(event)
        # Set column widths once the dialog is shown and properly sized
        self._set_column_widths()

    # ---------- Data loading ----------
    def _vendors_csv_path(self):
        return get_vendor_csv_path()

    def _normalize_vendor_number(self, raw):
        digits = "".join(ch for ch in (raw or "") if ch.isdigit())
        return digits.zfill(7) if digits else ""

    def _load_data(self):
        # Block signals during bulk loading for performance
        self.model.blockSignals(True)
        self.proxy.blockSignals(True)
        
        self.model.clear()
        self.model.setHorizontalHeaderLabels([
            "Vendor Name", "Vendor Number", "Vendor Identifier"
        ])

        # Load all vendor data from the single CSV (now includes optional identifier column)
        vendors = []
        csv_path = self._vendors_csv_path()
        print(f"[DEBUG] Loading vendor data from: {csv_path}")
        
        if os.path.exists(csv_path):
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                header_row = reader.fieldnames
                print(f"[DEBUG] CSV headers: {header_row}")
                for row_num, row in enumerate(reader):
                    # Debug raw row data for first few rows
                    if row_num < 10:
                        print(f"[DEBUG] Raw CSV row {row_num}: {dict(row)}")
                    
                    vendor_data = {
                        "name": (row.get("Vendor Name", "") or "").strip(),
                        "number": (row.get("Vendor No. (Sage)", "") or "").strip(),
                        "identifier": (row.get("Identifier", "") or "").strip(),
                    }
                    vendors.append(vendor_data)
                    
                    # Debug processed data for first few rows and any with identifiers
                    if row_num < 10 or vendor_data["identifier"]:
                        print(f"[DEBUG] Processed row {row_num}: {vendor_data}")
                        if vendor_data["identifier"]:
                            print(f"[DEBUG] *** Found identifier: '{vendor_data['identifier']}' for vendor '{vendor_data['name']}'")
        else:
            print(f"[DEBUG] CSV file does not exist: {csv_path}")

        # Sort by vendor name, then by identifier (so multiple identifiers for same vendor are grouped)
        vendors.sort(key=lambda v: (v["name"].casefold(), v["identifier"].casefold()))

        print(f"[DEBUG] Loaded {len(vendors)} vendor rows from CSV")

        # Add all rows and set the data (without triggering updates)
        for i, v in enumerate(vendors):
            row = self.model.rowCount()
            self.model.insertRow(row)
            self._set_item_no_tracking(row, 0, v["name"])
            self._set_item_no_tracking(row, 1, v["number"])
            self._set_item_no_tracking(row, 2, v["identifier"])
            
            # Debug every vendor that should have an identifier based on the CSV data
            if v["identifier"]:
                print(f"[DEBUG] ✓ Setting identifier '{v['identifier']}' for vendor '{v['name']}' at model row {row}")
            else:
                # Only log first 10 without identifiers to avoid spam
                if i < 10:
                    print(f"[DEBUG] ✗ No identifier for vendor '{v['name']}' at model row {row}")
            
            # Double-check what actually got set in the model
            if v["identifier"]:
                item = self.model.item(row, 2)
                actual_text = item.text() if item else "NO_ITEM"
                print(f"[DEBUG] Model verification - Expected: '{v['identifier']}', Actually set: '{actual_text}'")

        # Re-enable signals and trigger single update
        self.model.blockSignals(False)
        self.proxy.blockSignals(False)
        
        # Trigger the view to display the data
        self.proxy.invalidate()
        self.table.sortByColumn(-1, Qt.AscendingOrder)
        self.table.horizontalHeader().setSortIndicatorShown(False)
        
        # Set column widths to 40%, 20%, 40%
        self._set_column_widths()
        
        # Initialize original tracking after loading (no highlighting needed)
        self.original = {}
        for r in range(self.model.rowCount()):
            for c in range(3):
                item = self.model.item(r, c)
                if item:
                    self.original[(r, c)] = item.text()
        
        self._update_dirty()

    def _set_column_widths(self):
        """Set column widths to 40%, 20%, 40% of table width."""
        table_width = self.table.width()
        if table_width > 0:  # Make sure table has been sized
            header = self.table.horizontalHeader()
            # Temporarily disable stretch to set specific widths
            header.setStretchLastSection(False)
            
            # Set widths: 40%, 20%, 40%
            col1_width = int(table_width * 0.40)
            col2_width = int(table_width * 0.20)
            col3_width = int(table_width * 0.40)
            
            header.resizeSection(0, col1_width)  # Vendor Name: 40%
            header.resizeSection(1, col2_width)  # Vendor Number: 20%
            header.resizeSection(2, col3_width)  # Vendor Identifier: 40%
            
            # Re-enable stretch for the last section
            header.setStretchLastSection(True)

    def _set_item_no_tracking(self, row, col, text):
        """Set item without change tracking or highlighting (for initial load)."""
        text = str(text) if text is not None else ""
        item = QStandardItem(text)
        item.setData(text, Qt.DisplayRole)
        item.setEditable(True)
        # No background color - keep default
        self.model.setItem(row, col, item)
    
    def _set_item(self, row, col, text):
        """Set item with change tracking (for user edits)."""
        text = str(text) if text is not None else ""
        item = QStandardItem(text)
        item.setData(text, Qt.DisplayRole)
        item.setEditable(True)
        # No highlighting - keep default white background
        self.model.setItem(row, col, item)
        self.original[(row, col)] = text

    # ---------- Editing helpers ----------
    def add_row(self):
        row = self.model.rowCount()
        # Create the row first
        self.model.insertRow(row)
        for col in range(3):
            self._set_item(row, col, "")
        self._update_dirty()
        # Schedule validation for the new row
        self._schedule_validation()

    def delete_row(self):
        # Get current selected row (need to map from view to source)
        selection = self.table.selectionModel().currentIndex()
        if not selection.isValid():
            return
        
        # Map proxy index to source index
        source_index = self.proxy.mapToSource(selection)
        source_row = source_index.row()
        
        res = QMessageBox.warning(
            self,
            "Delete Vendor",
            "Are you sure you want to delete this vendor?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if res != QMessageBox.Yes:
            return
        res = QMessageBox.warning(
            self,
            "Delete Vendor",
            "Deleting will permanently remove this Vendor. Do you still wish to continue?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if res != QMessageBox.Yes:
            return
        
        self.model.removeRow(source_row)
        
        # Update original tracking
        new_orig = {}
        for (r, c), val in self.original.items():
            if r < source_row:
                new_orig[(r, c)] = val
            elif r > source_row:
                new_orig[(r - 1, c)] = val
        self.original = new_orig
        self._update_dirty()
        self._dirty = True

    def _handle_item_changed(self, item):
        key = (item.row(), item.column())
        orig = self.original.get(key, "")
        new_text = item.text().strip()
        
        # Debug changes, especially to identifiers
        if item.column() == 2:  # Identifier column
            vendor_name = ""
            name_item = self.model.item(item.row(), 0)
            if name_item:
                vendor_name = name_item.text().strip()
            print(f"[DEBUG] Identifier changed for vendor '{vendor_name}': '{orig}' → '{new_text}'")
        
        # No highlighting - just track changes
        self._update_dirty()
        # Schedule validation when items change
        self._schedule_validation()
    
    def _schedule_validation(self):
        """Schedule vendor number validation to run after a short delay."""
        if self._validation_timer is None:
            self._validation_timer = QTimer()
            self._validation_timer.timeout.connect(self._validate_vendor_numbers)
            self._validation_timer.setSingleShot(True)
        self._validation_timer.start(500)  # 500ms delay
    
    def _validate_vendor_numbers(self):
        """Check for rows with vendor names but no vendor numbers and warn the user."""
        invalid_rows = []
        
        for row in range(self.model.rowCount()):
            name_item = self.model.item(row, 0)
            number_item = self.model.item(row, 1)
            
            name = name_item.text().strip() if name_item else ""
            number = number_item.text().strip() if number_item else ""
            
            # Check for invalid rows (name without number) - no highlighting
            if name and not number:
                invalid_rows.append(row + 1)  # 1-based for user display
        
        if invalid_rows:
            if len(invalid_rows) == 1:
                msg = (f"Row {invalid_rows[0]} has a Vendor Name but no Vendor Number.\n\n"
                       f"You must either:\n"
                       f"• Enter a Vendor Number for this row, or\n"
                       f"• Delete this row\n\n"
                       f"Rows with Vendor Names require Vendor Numbers to be saved.")
            else:
                row_list = ", ".join(str(r) for r in invalid_rows)
                msg = (f"Rows {row_list} have Vendor Names but no Vendor Numbers.\n\n"
                       f"You must either:\n"
                       f"• Enter Vendor Numbers for these rows, or\n"
                       f"• Delete these rows\n\n"
                       f"Rows with Vendor Names require Vendor Numbers to be saved.")
            
            QMessageBox.warning(
                self,
                "Missing Vendor Numbers",
                msg,
                QMessageBox.Ok
            )

    def _update_dirty(self):
        dirty = False
        for (row, col), orig in self.original.items():
            cur_item = self.model.item(row, col)
            cur = cur_item.text() if cur_item else ""
            if cur != orig:
                dirty = True
                break
        self._dirty = dirty

    # ---------- Filtering ----------
    def _apply_filter(self, text):
        """Filter the table using the proxy model."""
        self.proxy.setFilterKeyColumn(-1)  # Search all columns
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)
        self.proxy.setFilterFixedString(text)

    # ---------- Saving ----------
    def _gather_rows(self):
        rows = []
        mapping = {}
        invalid_rows = []
        
        print(f"[DEBUG] Gathering rows from {self.model.rowCount()} rows in model...")
        
        for r in range(self.model.rowCount()):
            name_item = self.model.item(r, 0)
            num_item = self.model.item(r, 1)
            id_item = self.model.item(r, 2)
            
            name = name_item.text().strip() if name_item else ""
            number = self._normalize_vendor_number(num_item.text() if num_item else "")
            ident = id_item.text().strip() if id_item else ""
            
            print(f"[DEBUG] Row {r}: name='{name}', number='{number}', identifier='{ident}'")
            
            # Skip completely empty rows
            if not name and not number and not ident:
                print(f"[DEBUG] Skipping completely empty row {r}")
                continue
            
            # Check for invalid rows (name without number)
            if name and not number:
                print(f"[DEBUG] Invalid row {r}: has name but no number")
                invalid_rows.append(r + 1)  # 1-based for user display
                continue
            
            # Only add valid rows
            if name and number:  # Both name and number required
                print(f"[DEBUG] Adding valid row {r}: '{name}' with number '{number}' and identifier '{ident}'")
                rows.append({
                    "Vendor Name": name, 
                    "Vendor No. (Sage)": number,
                    "Identifier": ident  # Can be empty
                })
        
        if invalid_rows:
            if len(invalid_rows) == 1:
                raise ValueError(f"Row {invalid_rows[0]} has a Vendor Name but no Vendor Number. "
                               f"Please enter a Vendor Number or delete this row before saving.")
            else:
                row_list = ", ".join(str(r) for r in invalid_rows)
                raise ValueError(f"Rows {row_list} have Vendor Names but no Vendor Numbers. "
                               f"Please enter Vendor Numbers or delete these rows before saving.")
        
        return rows

    def save(self):
        try:
            headers = ["Vendor Name", "Vendor Number", "Vendor Identifier"]
            changes = []
            for (row, col), orig in self.original.items():
                cur_item = self.model.item(row, col)
                cur = cur_item.text() if cur_item else ""
                if cur != orig:
                    orig_disp = orig or "(empty)"
                    cur_disp = cur or "(empty)"
                    changes.append(f"{headers[col]}: {orig_disp} -> {cur_disp}")

            if changes:
                msg = (
                    "Are you sure you want to make the following changes?\n\n"
                    "Original -> Edited\n" + "\n".join(changes)
                )
                res = QMessageBox.question(
                    self,
                    "Confirm Changes",
                    msg,
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if res != QMessageBox.Yes:
                    return False
            
            rows = self._gather_rows()
            rows.sort(key=lambda r: (r["Vendor Name"].casefold(), r["Identifier"].casefold()))
            
            csv_path = self._vendors_csv_path()
            print(f"[DEBUG] Saving {len(rows)} rows to CSV: {csv_path}")
            with open(csv_path, "w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=["Vendor No. (Sage)", "Vendor Name", "Identifier"])
                writer.writeheader()
                for r in rows:
                    writer.writerow(r)
            
            print(f"[DEBUG] Successfully saved {len(rows)} vendor rows to CSV")
            
            # Reset tracking (no highlighting)
            print("[DEBUG] Resetting original tracking after save...")
            self.original = {}
            for r in range(self.model.rowCount()):
                for c in range(3):
                    item = self.model.item(r, c)
                    if item:
                        text = item.text()
                        self.original[(r, c)] = text
                        if c == 2:  # Identifier column
                            print(f"[DEBUG] Tracking identifier for row {r}: '{text}'")
            self._update_dirty()
            
            # Emit signal to notify that vendor list was updated
            self.vendor_list_updated.emit()
            return True
            
        except ValueError as e:
            QMessageBox.warning(
                self,
                "Validation Error",
                str(e),
                QMessageBox.Ok
            )
            return False

    def _save_and_close(self):
        if self.save():
            self.accept()

    # ---------- Closing ----------
    def closeEvent(self, event):
        # Clean up validation timer
        if self._validation_timer:
            self._validation_timer.stop()
            
        if self._dirty:
            res = QMessageBox.question(
                self,
                "Unsaved Changes",
                "Save changes before closing?",
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Cancel,
            )
            if res == QMessageBox.Cancel:
                event.ignore()
                return
            if res == QMessageBox.Yes:
                if not self.save():
                    event.ignore()
                    return
        event.accept()