"""Dialogs for vendor selection and creation."""
import os
import fitz

from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QComboBox, QPushButton,
    QLineEdit, QMessageBox, QDialogButtonBox, QSplitter, QWidget
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from extractors.utils import get_vendor_list, load_manual_mapping
from extractors.vendor_name import save_manual_mapping
from views.pdf_viewer import InteractivePDFViewer

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