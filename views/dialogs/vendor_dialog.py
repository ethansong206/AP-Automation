"""Dialogs for vendor selection and creation."""
import os
import fitz
import csv

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton,
    QLineEdit, QMessageBox, QDialogButtonBox, QSplitter, QWidget,
    QHBoxLayout
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from extractors.utils import get_vendor_list, load_manual_mapping
from extractors.vendor_name import save_manual_mapping
from views.components.pdf_viewer import InteractivePDFViewer

# --- Helper Functions ---
def _vendors_csv_path() -> str:
    """
    Resolve vendors.csv path. Adjust if your project keeps it elsewhere.
    """
    # Try ../data/vendors.csv relative to this file
    here = os.path.dirname(os.path.abspath(__file__))
    # vendor_dialog.py typically lives under .../views/dialogs/
    project_root = os.path.abspath(os.path.join(here, "..", ".."))
    candidate = os.path.join(project_root, "data", "vendors.csv")
    if os.path.isfile(candidate):
        return candidate
    # Fallback: current working dir
    fallback = "vendors.csv"
    return fallback

def _normalize_vendor_number(raw: str) -> str:
    # Numeric only, pad left to 7
    digits = "".join(ch for ch in (raw or "") if ch.isdigit())
    return digits.zfill(7)

def _load_vendors_csv() -> list[dict]:
    path = _vendors_csv_path()
    rows = []
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8-sig", newline="") as f:
            r = csv.DictReader(f)
            # Expect: Vendor No. (Sage), Vendor Name
            for row in r:
                rows.append({
                    "Vendor No. (Sage)": _normalize_vendor_number(row.get("Vendor No. (Sage)", "")),
                    "Vendor Name": (row.get("Vendor Name", "") or "").strip(),
                })
    return rows

def _write_vendors_csv(rows: list[dict]) -> None:
    path = _vendors_csv_path()
    fieldnames = ["Vendor No. (Sage)", "Vendor Name"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({
                "Vendor No. (Sage)": _normalize_vendor_number(r.get("Vendor No. (Sage)", "")),
                "Vendor Name": (r.get("Vendor Name", "") or "").strip(),
            })

def _exists_vendor_name(rows: list[dict], name: str) -> bool:
    name_l = (name or "").strip().lower()
    return any((r.get("Vendor Name","") or "").strip().lower() == name_l for r in rows)

def _exists_vendor_name_and_no(rows: list[dict], name: str, vno: str) -> bool:
    name_l = (name or "").strip().lower()
    vno_n = _normalize_vendor_number(vno or "")
    return any(
        (r.get("Vendor Name","") or "").strip().lower() == name_l and
        _normalize_vendor_number(r.get("Vendor No. (Sage)", "")) == vno_n
        for r in rows
    )

def _append_vendor_csv(name: str, vno: str) -> None:
    rows = _load_vendors_csv()
    if _exists_vendor_name(rows, name):
        raise ValueError(f"Vendor '{name}' already exists. Select it from the drop-down.")
    if _exists_vendor_name_and_no(rows, name, vno):
        raise ValueError(
            f"Vendor '{name}' with number {_normalize_vendor_number(vno)} already exists. "
            "Select it from the drop-down."
        )
    rows.append({"Vendor Name": name.strip(), "Vendor No. (Sage)": _normalize_vendor_number(vno)})
    _write_vendors_csv(rows)

class VendorDialog(QDialog):
    """Dialog for adding a new vendor."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Create New Vendor")
        layout = QVBoxLayout(self)

        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("Enter new vendor name")
        self.confirm_input = QLineEdit()
        self.confirm_input.setPlaceholderText("Confirm new vendor name")

        self.error_label = QLabel("")
        self.error_label.setStyleSheet("color: red;")
        self.error_label.setVisible(False)

        layout.addWidget(QLabel("Vendor Name:"))
        layout.addWidget(self.name_input)
        layout.addWidget(QLabel("Confirm Vendor Name:"))
        layout.addWidget(self.confirm_input)
        layout.addWidget(self.error_label)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

        self.name_input.textChanged.connect(self.validate)
        self.confirm_input.textChanged.connect(self.validate)
        self.validate()

    def validate(self):
        """Validate the input fields."""
        name = self.name_input.text().strip()
        confirm = self.confirm_input.text().strip()
        save_btn = self.button_box.button(QDialogButtonBox.Save)
        if not name or not confirm:
            self.error_label.setVisible(False)
            save_btn.setEnabled(False)
        elif name != confirm:
            self.error_label.setText("Names do not match.")
            self.error_label.setVisible(True)
            save_btn.setEnabled(False)
        else:
            self.error_label.setVisible(False)
            save_btn.setEnabled(True)

    def get_name(self):
        """Get the entered vendor name."""
        return self.name_input.text().strip()


class VendorSelectDialog(QDialog):
    """Dialog for selecting vendors from a list or adding new ones."""
    
    def __init__(self, pdf_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Select Vendor")
        self.setMinimumSize(800, 600)
        self.pdf_path = pdf_path  # Save PDF path for identifier validation later

        # --- Vendor Dropdown Setup ---
        csv_vendors = get_vendor_list()
        manual_vendors = list(load_manual_mapping().values())
        combined = sorted(set(csv_vendors + manual_vendors), key=str.lower)

        self.combo = QComboBox()
        self.combo.addItems(combined)

        self.new_vendor_btn = QPushButton("Create New Vendor")
        self.new_vendor_btn.clicked.connect(self.add_new_vendor)

        # --- Identifier Entry ---
        self.identifier_input = QLineEdit()
        self.identifier_input.setPlaceholderText("Enter unique identifier (e.g. email address, customer #, etc.)")

        self.identifier_confirm = QLineEdit()
        self.identifier_confirm.setPlaceholderText("Confirm unique identifier")
        self.identifier_confirm.textChanged.connect(self.check_identifiers_match)

        self.identifier_error_label = QLabel("")
        self.identifier_error_label.setStyleSheet("color: red;")
        self.identifier_error_label.setVisible(False)

        # --- Save & Cancel ---
        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.save)
        self.button_box.rejected.connect(self.reject)

        # --- Left Panel Layout ---
        left_layout = QVBoxLayout()

        left_font = QFont()
        left_font.setPointSize(left_font.pointSize() + 2)

        label_select = QLabel("Select a vendor from the list:")
        label_select.setFont(left_font)
        left_layout.addWidget(label_select)

        self.combo.setFont(left_font)
        left_layout.addWidget(self.combo)

        or_label = QLabel("--- OR ---")
        or_label.setAlignment(Qt.AlignCenter)
        or_label.setFont(left_font)
        left_layout.addWidget(or_label)

        self.new_vendor_btn.setFont(left_font)
        left_layout.addWidget(self.new_vendor_btn)

        left_layout.addSpacing(20)
        sep_label = QLabel("--------------------------------------------------")
        sep_label.setAlignment(Qt.AlignCenter)
        sep_label.setFont(left_font)
        left_layout.addWidget(sep_label)
        left_layout.addSpacing(20)

        label_unique = QLabel("Unique Identifier:")
        label_unique.setFont(left_font)
        left_layout.addWidget(label_unique)

        self.identifier_input.setFont(left_font)
        left_layout.addWidget(self.identifier_input)

        label_confirm = QLabel("Confirm Identifier:")
        label_confirm.setFont(left_font)
        left_layout.addWidget(label_confirm)

        self.identifier_confirm.setFont(left_font)
        left_layout.addWidget(self.identifier_confirm)

        self.identifier_error_label.setFont(left_font)
        left_layout.addWidget(self.identifier_error_label)

        left_layout.addStretch()
        self.button_box.setFont(left_font)
        left_layout.addWidget(self.button_box)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        # --- PDF Viewer ---
        viewer = InteractivePDFViewer(pdf_path)

        splitter = QSplitter()
        splitter.addWidget(left_widget)
        splitter.addWidget(viewer)
        splitter.setSizes([300, 500])

        main_layout = QVBoxLayout()
        main_layout.addWidget(splitter)
        self.setLayout(main_layout)

    def add_new_vendor(self):
        """Open dialog to add a new vendor."""
        dialog = VendorDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            name = dialog.get_name()
            # Check for duplicates (case-insensitive)
            existing_names = [self.combo.itemText(i).strip().lower() for i in range(self.combo.count())]
            if name.lower() in existing_names:
                QMessageBox.critical(self, "Duplicate Vendor",
                    f"The vendor '{name}' already exists.\nPlease check the drop-down menu.")
                return
            self.combo.addItem(name)
            self.combo.setCurrentText(name)

    def check_identifiers_match(self):
        """Verify that entered identifiers match."""
        id1 = self.identifier_input.text().strip()
        id2 = self.identifier_confirm.text().strip()
        if id1 and id2 and id1 != id2:
            self.identifier_error_label.setText("Identifiers do not match.")
            self.identifier_error_label.setVisible(True)
        else:
            self.identifier_error_label.setVisible(False)

    def save(self):
        """Save the vendor selection and identifier."""
        vendor = self.combo.currentText().strip()
        id1 = self.identifier_input.text().strip()
        id2 = self.identifier_confirm.text().strip()

        if not vendor:
            QMessageBox.critical(self, "Missing Vendor", "Please select or enter a vendor.")
            return

        if not id1 or not id2:
            QMessageBox.critical(self, "Missing Identifier", "Please enter and confirm the identifier.")
            return

        if id1 != id2:
            QMessageBox.critical(self, "Mismatch", "The identifiers do not match.")
            return

        # --- Validate Identifier in PDF ---
        try:
            doc = fitz.open(self.pdf_path)
            full_text = "\n".join(page.get_text() for page in doc)
            if id1.lower() not in full_text.lower():
                QMessageBox.critical(self, "Identifier Not Found",
                    f"The string '{id1}' does not appear in the PDF.\n"
                    "Please double-check for typos or try a different identifier.")
                return
        except Exception as e:
            QMessageBox.critical(self, "PDF Read Error", f"Unable to read PDF:\n{e}")
            return

        # Confirm save
        confirm = QMessageBox.question(
            self, "Confirm Save",
            f"Are you sure you want to map:\n\nVendor: {vendor}\nIdentifier: {id1}",
            QMessageBox.Yes | QMessageBox.Cancel
        )
        if confirm != QMessageBox.Yes:
            return

        # --- Save Mapping ---
        save_manual_mapping(id1.lower(), vendor)
        QMessageBox.information(
            self, "Mapping Saved",
            f"Future invoices containing '{id1}' will map to '{vendor}'."
        )
        self.accept()

    def selected_vendor(self):
        """Return the selected vendor name."""
        return self.combo.currentText().strip()

    def get_identifier(self):
        """Return the entered identifier."""
        return self.identifier_input.text().strip()

class AddVendorFlow(QDialog):
    """
    Guided flow used by Manual Entry when adding a vendor:
    1) Vendor Name (x2)
    2) Vendor Number (required, numeric only, 7 digits; modeless lookup button)
    3) Identifier (optional): Save (verify in PDF) or Skip & Save
    """
    def __init__(self, pdf_path: str, parent=None, prefill_vendor_name: str = ""):
        super().__init__(parent)
        self.pdf_path = pdf_path
        self._final_vendor_name = None
        self.setWindowTitle("Add Vendor")
        self.setMinimumSize(560, 420)

        layout = QVBoxLayout(self)

        # --- Step 1: Vendor Name x2
        layout.addWidget(QLabel("Vendor Name:"))
        self.name_input = QLineEdit(self)
        self.name_input.setPlaceholderText("Type vendor name")
        if prefill_vendor_name:
            self.name_input.setText(prefill_vendor_name)
        layout.addWidget(self.name_input)

        layout.addWidget(QLabel("Confirm Vendor Name:"))
        self.name_confirm = QLineEdit(self)
        self.name_confirm.setPlaceholderText("Re-type vendor name")
        layout.addWidget(self.name_confirm)

        # --- Step 2: Vendor Number (required)
        layout.addWidget(QLabel("Vendor Number (7 digits):"))
        self.vno_input = QLineEdit(self)
        self.vno_input.setPlaceholderText("Digits only; will left-pad to 7")
        layout.addWidget(self.vno_input)

        # --- Step 3: Identifier (optional)
        layout.addWidget(QLabel("Identifier (optional):"))
        self.id_input = QLineEdit(self)
        self.id_input.setPlaceholderText("Unique identifier (e.g., email fragment, acct #)")
        layout.addWidget(self.id_input)

        layout.addWidget(QLabel("Confirm Identifier:"))
        self.id_confirm = QLineEdit(self)
        self.id_confirm.setPlaceholderText("Re-type identifier")
        layout.addWidget(self.id_confirm)

        # Buttons: Save (with identifier) / Skip & Save (no identifier)
        btns = QHBoxLayout()
        self.save_btn = QPushButton("Save (with Identifier)")
        self.skip_btn = QPushButton("Skip and Save (no Identifier)")
        self.cancel_btn = QPushButton("Cancel")
        btns.addWidget(self.save_btn)
        btns.addWidget(self.skip_btn)
        btns.addStretch(1)
        btns.addWidget(self.cancel_btn)
        layout.addLayout(btns)

        # Signals
        self.save_btn.clicked.connect(self._save_with_identifier)
        self.skip_btn.clicked.connect(self._skip_and_save)
        self.cancel_btn.clicked.connect(self.reject)

    # --- Public API used by Manual Entry to read what was added ---
    def get_final_vendor_name(self):
        return self._final_vendor_name

    # --- Internals ---
    def _validate_name(self) -> str | None:
        name = (self.name_input.text() or "").strip()
        confirm = (self.name_confirm.text() or "").strip()
        if not name or not confirm:
            QMessageBox.warning(self, "Missing Name", "Please enter and confirm the vendor name.")
            return None
        if name != confirm:
            QMessageBox.warning(self, "Name Mismatch", "Vendor names do not match.")
            return None
        return name

    def _validate_and_normalize_vno(self) -> str | None:
        raw = (self.vno_input.text() or "").strip()
        if not raw or not raw.isdigit():
            QMessageBox.warning(self, "Invalid Vendor Number", "Vendor Number must be digits only.")
            return None
        return _normalize_vendor_number(raw)

    def _check_duplicates_or_raise(self, name: str, vno: str) -> None:
        rows = _load_vendors_csv()
        # Rule: block duplicate names (case-insensitive)
        if _exists_vendor_name(rows, name):
            raise ValueError(
                f"Vendor '{name}' already exists in vendors.csv.\n"
                "Please select it from the drop-down."
            )
        # Rule: block duplicate (name+number)
        if _exists_vendor_name_and_no(rows, name, vno):
            raise ValueError(
                f"Vendor '{name}' with number {vno} already exists in vendors.csv.\n"
                "Please select it from the drop-down."
            )

    def _append_name_and_number(self, name: str, vno: str) -> None:
        _append_vendor_csv(name, vno)

    # --- Save paths ---
    def _skip_and_save(self):
        """
        No identifier: write to vendors.csv only (after duplicate checks).
        """
        name = self._validate_name()
        if not name:
            return
        vno = self._validate_and_normalize_vno()
        if not vno:
            return

        try:
            self._check_duplicates_or_raise(name, vno)
            self._append_name_and_number(name, vno)
        except Exception as e:
            QMessageBox.critical(self, "Cannot Save Vendor", str(e))
            return

        self._final_vendor_name = name
        QMessageBox.information(self, "Vendor Added", f"Added '{name}' (No. {vno}) to vendors.csv.")
        self.accept()

    def _save_with_identifier(self):
        """
        Identifier provided: still must pass vendors.csv duplicate checks and be added there.
        Then add identifier->vendor to manual_vendor_map.json IF identifier is found in the PDF
        AND the (identifier) is not already mapped.
        """
        name = self._validate_name()
        if not name:
            return
        vno = self._validate_and_normalize_vno()
        if not vno:
            return

        id1 = (self.id_input.text() or "").strip()
        id2 = (self.id_confirm.text() or "").strip()
        if not id1 or not id2:
            QMessageBox.warning(self, "Missing Identifier", "Please enter and confirm the identifier, or use Skip & Save.")
            return
        if id1 != id2:
            QMessageBox.warning(self, "Identifier Mismatch", "Identifiers do not match.")
            return

        # Check identifier exists in PDF text
        try:
            doc = fitz.open(self.pdf_path) if self.pdf_path and os.path.exists(self.pdf_path) else None
            full_text = ""
            if doc:
                full_text = "\n".join(page.get_text() for page in doc)
            if not full_text or id1.lower() not in full_text.lower():
                # Warn and let user stay here (they can retry or use Skip & Save)
                QMessageBox.warning(self, "Identifier Not Found",
                    f"‘{id1}’ does not appear in this PDF.\n"
                    "You can correct it or click ‘Skip & Save’ to proceed without an identifier.")
                return
        except Exception as e:
            QMessageBox.warning(self, "PDF Read Error",
                f"Unable to read PDF for identifier check:\n{e}\n"
                "You can correct it or click ‘Skip & Save’.")
            return

        # Now enforce duplicate rules and write CSV first
        try:
            self._check_duplicates_or_raise(name, vno)
            self._append_name_and_number(name, vno)
        except Exception as e:
            QMessageBox.critical(self, "Cannot Save Vendor", str(e))
            return

        # Write to manual_vendor_map.json if identifier not already mapped
        manual_map = load_manual_mapping()  # dict: identifier -> vendor name
        key = id1.lower()
        if key in manual_map:
            # If already mapped to same vendor, fine; if different, warn
            if manual_map[key].strip().lower() != name.strip().lower():
                QMessageBox.warning(
                    self, "Identifier Already Mapped",
                    f"The identifier ‘{id1}’ is already mapped to ‘{manual_map[key]}’. "
                    "It was NOT changed."
                )
                # We still accept because CSV was successfully written.
        else:
            save_manual_mapping(key, name)

        self._final_vendor_name = name
        QMessageBox.information(
            self, "Vendor & Identifier Saved",
            f"Added '{name}' (No. {vno}) to vendors.csv and mapped identifier."
        )
        self.accept()