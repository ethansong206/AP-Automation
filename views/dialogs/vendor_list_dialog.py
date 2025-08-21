import os
import csv
import json

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QTableWidget, QTableWidgetItem, QPushButton,
    QHBoxLayout, QMessageBox
)
from PyQt5.QtGui import QColor

from extractors.utils import resource_path


class VendorListDialog(QDialog):
    """Editable vendor list merging vendors.csv and manual_vendor_map.json."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vendor List")
        self.resize(700, 500)

        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels([
            "Vendor Name", "Vendor Number", "Vendor Identifier"
        ])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.itemChanged.connect(self._handle_item_changed)

        btn_layout = QHBoxLayout()
        self.add_row_btn = QPushButton("Add Row")
        self.save_btn = QPushButton("Save")
        self.cancel_btn = QPushButton("Cancel")
        self.add_row_btn.clicked.connect(self.add_row)
        self.save_btn.clicked.connect(self._save_and_close)
        self.cancel_btn.clicked.connect(self.close)
        btn_layout.addWidget(self.add_row_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.save_btn)
        btn_layout.addWidget(self.cancel_btn)

        layout = QVBoxLayout(self)
        layout.addWidget(self.table)
        layout.addLayout(btn_layout)

        self._dirty = False
        self.original = {}
        self._load_data()

    # ---------- Data loading ----------
    def _vendors_csv_path(self):
        return resource_path("data/vendors.csv")

    def _vendor_map_path(self):
        return resource_path("data/manual_vendor_map.json")

    def _normalize_vendor_number(self, raw):
        digits = "".join(ch for ch in (raw or "") if ch.isdigit())
        return digits.zfill(7) if digits else ""

    def _load_data(self):
        self.table.blockSignals(True)
        self.table.setRowCount(0)

        vendors = []
        csv_path = self._vendors_csv_path()
        if os.path.exists(csv_path):
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    vendors.append({
                        "name": (row.get("Vendor Name", "") or "").strip(),
                        "number": (row.get("Vendor No. (Sage)", "") or "").strip(),
                    })

        identifier_map = {}
        map_path = self._vendor_map_path()
        if os.path.exists(map_path):
            try:
                with open(map_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for ident, name in data.items():
                        if name not in identifier_map:
                            identifier_map[name] = ident
            except Exception:
                identifier_map = {}

        for v in vendors:
            row = self.table.rowCount()
            self.table.insertRow(row)
            self._set_item(row, 0, v["name"])
            self._set_item(row, 1, v["number"])
            self._set_item(row, 2, identifier_map.get(v["name"], ""))

        self.table.blockSignals(False)
        self._update_dirty()

    def _set_item(self, row, col, text):
        item = QTableWidgetItem(text)
        self.table.setItem(row, col, item)
        self.original[(row, col)] = text

    # ---------- Editing helpers ----------
    def add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        for col in range(3):
            self._set_item(row, col, "")
        self._update_dirty()

    def _handle_item_changed(self, item):
        key = (item.row(), item.column())
        orig = self.original.get(key, "")
        if item.text() != orig:
            item.setBackground(QColor("yellow"))
        else:
            item.setBackground(QColor("white"))
        self._update_dirty()

    def _update_dirty(self):
        dirty = False
        for (row, col), orig in self.original.items():
            cur_item = self.table.item(row, col)
            cur = cur_item.text() if cur_item else ""
            if cur != orig:
                dirty = True
                break
        self._dirty = dirty

    # ---------- Saving ----------
    def _gather_rows(self):
        rows = []
        mapping = {}
        for r in range(self.table.rowCount()):
            name_item = self.table.item(r, 0)
            num_item = self.table.item(r, 1)
            id_item = self.table.item(r, 2)
            name = name_item.text().strip() if name_item else ""
            number = self._normalize_vendor_number(num_item.text() if num_item else "")
            ident = id_item.text().strip() if id_item else ""
            if not name and not number and not ident:
                continue
            rows.append({"Vendor Name": name, "Vendor No. (Sage)": number})
            if ident:
                mapping[ident] = name
        return rows, mapping

    def save(self):
        rows, mapping = self._gather_rows()
        csv_path = self._vendors_csv_path()
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["Vendor No. (Sage)", "Vendor Name"])
            writer.writeheader()
            for r in rows:
                writer.writerow(r)
        map_path = self._vendor_map_path()
        with open(map_path, "w", encoding="utf-8") as f:
            json.dump(mapping, f, indent=2)
        # reset tracking
        self.original = {}
        for r in range(self.table.rowCount()):
            for c in range(3):
                item = self.table.item(r, c)
                if item:
                    self.original[(r, c)] = item.text()
                    item.setBackground(QColor("white"))
        self._update_dirty()
        return True

    def _save_and_close(self):
        if self.save():
            self.accept()

    # ---------- Closing ----------
    def closeEvent(self, event):
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