import os
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QDateEdit,
    QPushButton, QDialogButtonBox, QSplitter, QWidget, QFormLayout,
    QComboBox, QMessageBox, QCompleter, QListWidget
)
from PyQt5.QtCore import Qt, QDate
from PyQt5.QtGui import QBrush

from views.components.pdf_viewer import InteractivePDFViewer
from views.dialogs.vendor_dialog import VendorDialog
from extractors.utils import get_vendor_list, calculate_discount_due_date, calculate_discounted_total

class ManualEntryDialog(QDialog):
    """Dialog for manual entry of invoice fields with PDF viewer.

    This version can handle multiple files within a single dialog.  A list
    of uploaded files is shown on the left allowing direct navigation without
    closing and reopening the dialog.
    """
    def __init__(self, pdf_paths, parent=None, values_list=None, start_index=0):
        super().__init__(parent)
        self.setWindowTitle("Manual Entry")
        self.setMinimumSize(1100, 600)

        # Store paths and values for all files
        self.pdf_paths = pdf_paths
        self.values_list = values_list or [[""] * 8 for _ in pdf_paths]
        self.current_index = start_index
        self.save_changes = False

        # --- File list on the far left ---
        self.file_list = QListWidget()
        for path in pdf_paths:
            self.file_list.addItem(os.path.basename(path) if path else "")
        self.file_list.currentRowChanged.connect(self.switch_to_index)
        self.viewed_files = set()

        # --- Form fields ---
        form_layout = QFormLayout()
        self.fields = {}

        # 1. Replace Vendor Name with dropdown + button
        vendor_layout = QHBoxLayout()
        self.vendor_combo = QComboBox()
        self.vendor_combo.setEditable(True)
        self.vendor_combo.setInsertPolicy(QComboBox.NoInsert)
        self.load_vendors()
        #Enable popup suggestions while typing
        completer = self.vendor_combo.completer()
        if completer:
            completer.setCompletionMode(QCompleter.PopupCompletion)
        vendor_layout.addWidget(self.vendor_combo, 1)
        
        self.add_vendor_btn = QPushButton("New Vendor")
        self.add_vendor_btn.clicked.connect(self.add_new_vendor)
        vendor_layout.addWidget(self.add_vendor_btn)
        
        form_layout.addRow(QLabel("Vendor Name:"), vendor_layout)
        self.fields["Vendor Name"] = self.vendor_combo

        # 2. Add regular fields
        self.fields["Invoice Number"] = QLineEdit()
        form_layout.addRow(QLabel("Invoice Number:"), self.fields["Invoice Number"])
        
        self.fields["PO Number"] = QLineEdit()
        form_layout.addRow(QLabel("PO Number:"), self.fields["PO Number"])

        # 3. Date fields with MM/DD/YYYY format
        self.fields["Invoice Date"] = QDateEdit()
        self.fields["Invoice Date"].setCalendarPopup(True)
        self.fields["Invoice Date"].setDisplayFormat("MM/dd/yyyy")
        self.fields["Invoice Date"].setDate(QDate.currentDate())
        form_layout.addRow(QLabel("Invoice Date:"), self.fields["Invoice Date"])

        self.fields["Discount Terms"] = QLineEdit()
        form_layout.addRow(QLabel("Discount Terms:"), self.fields["Discount Terms"])

        # 4. Add Due Date with Calculate button
        due_date_layout = QHBoxLayout()
        self.fields["Due Date"] = QDateEdit()
        self.fields["Due Date"].setCalendarPopup(True)
        self.fields["Due Date"].setDisplayFormat("MM/dd/yyyy")
        self.fields["Due Date"].setDate(QDate.currentDate())
        due_date_layout.addWidget(self.fields["Due Date"], 1)
        
        self.calc_due_date_btn = QPushButton("Calculate")
        self.calc_due_date_btn.setToolTip("Calculate from Discount Terms")
        self.calc_due_date_btn.clicked.connect(self.calculate_due_date)
        due_date_layout.addWidget(self.calc_due_date_btn)
        
        form_layout.addRow(QLabel("Due Date:"), due_date_layout)

        # 5. Add Discounted Total with Calculate button
        disc_total_layout = QHBoxLayout()
        self.fields["Discounted Total"] = QLineEdit()
        disc_total_layout.addWidget(self.fields["Discounted Total"], 1)
        
        self.calc_disc_total_btn = QPushButton("Calculate")
        self.calc_disc_total_btn.setToolTip("Calculate from Discount Terms")
        self.calc_disc_total_btn.clicked.connect(self.calculate_discounted_total)
        disc_total_layout.addWidget(self.calc_disc_total_btn)
        
        form_layout.addRow(QLabel("Discounted Total:"), disc_total_layout)

        # 6. Total Amount field
        self.fields["Total Amount"] = QLineEdit()
        form_layout.addRow(QLabel("Total Amount:"), self.fields["Total Amount"])

        # Standard button styling for action buttons
        primary_button_style = (
            "QPushButton {"
            "background-color: #5E6F5E;"
            "color: white;"
            "border-radius: 4px;"
            "padding: 6px 12px;"
            "font-weight: bold;"
            "}"
            "QPushButton:hover { background-color: #3f6193; }"
            "QPushButton:pressed { background-color: #345480; }"
        )
        for btn in (self.add_vendor_btn, self.calc_due_date_btn, self.calc_disc_total_btn):
            btn.setStyleSheet(primary_button_style)

        # --- Navigation Buttons ---
        arrow_layout = QHBoxLayout()
        arrow_layout.addStretch()

        self.prev_button = QPushButton("←")
        self.next_button = QPushButton("→")
        
        button_style = (
            "QPushButton {"
            "background-color: #5E6F5E;"
            "color: #f0f0f0;"
            "border: 1px solid #3E4F3E;"
            "font-size: 28px;"
            "padding: 10px;"
            "}"
            "QPushButton:hover { background-color: #546454; }"
            "QPushButton:pressed { background-color: #485848; }"
            "QPushButton:disabled { background-color: #bbbbbb; color: #666666; }"
        )
        self.prev_button.setStyleSheet(button_style)
        self.next_button.setStyleSheet(button_style)
        size = 60
        self.prev_button.setFixedSize(size, size)
        self.next_button.setFixedSize(size, size)
        self.prev_button.clicked.connect(self.show_prev)
        self.next_button.clicked.connect(self.show_next)
        arrow_layout.addWidget(self.prev_button)
        arrow_layout.addWidget(self.next_button)
        arrow_layout.addStretch()

        # Combine the form and navigation buttons in a vertical layout
        left_layout = QVBoxLayout()
        left_layout.addLayout(form_layout)
        left_layout.addSpacing(20)
        left_layout.addLayout(arrow_layout)

        left_widget = QWidget()
        left_widget.setLayout(left_layout)

        # --- Right: PDF Viewer ---
        self.viewer = InteractivePDFViewer(self.pdf_paths[self.current_index])

        # --- Splitter Layout ---
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.addWidget(self.file_list)
        self.splitter.addWidget(left_widget)
        self.splitter.addWidget(self.viewer)
        self.splitter.setSizes([150, 350, 550])
        # Ensure the PDF viewer expands to take remaining space
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setStretchFactor(2, 1)

        # --- Dialog Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.on_save)
        button_box.rejected.connect(self.reject)
        for btn in button_box.buttons():
            btn.setStyleSheet(primary_button_style)

        # --- Content Layout ---
        content_layout = QVBoxLayout()
        content_layout.addWidget(self.splitter)
        content_layout.addWidget(button_box)

        self.setLayout(content_layout)

        # Load first invoice data
        self.load_invoice(self.current_index)

        # Highlight empty fields initially and update on change
        for label, widget in self.fields.items():
            if isinstance(widget, QLineEdit):
                widget.textChanged.connect(self._highlight_empty_fields)
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self._highlight_empty_fields)
            elif isinstance(widget, QDateEdit):
                widget.dateChanged.connect(lambda _, l=label: self._on_date_changed(l))

    def save_current_invoice(self):
        """Store current field values into values_list."""
        if not self.values_list:
            return
        self.values_list[self.current_index] = self.get_data()

    def load_invoice(self, index):
        """Load invoice data at the given index into the form."""
        self.current_index = index
        self.mark_file_viewed(index)
        values = self.values_list[index]

        self.vendor_combo.setCurrentText(values[0])
        self.fields["Invoice Number"].setText(values[1])
        self.fields["PO Number"].setText(values[2])

        # Invoice Date
        self.fields["Invoice Date"].setDate(QDate.currentDate())
        invoice_date = values[3]
        try:
            date_obj = QDate.fromString(invoice_date, "MM/dd/yy")

            if date_obj.isValid() and date_obj.year() < 2000:
                year = date_obj.year() % 100
                date_obj = QDate(2000 + year, date_obj.month(), date_obj.day())
            if date_obj.isValid():
                self.fields["Invoice Date"].setDate(date_obj)
        except Exception as e:
            print(f"Error parsing invoice date: {e}")
            
        self.fields["Discount Terms"].setText(values[4])

        # Due Date
        self.fields["Due Date"].setDate(QDate.currentDate())
        due_date = values[5]
        if due_date.strip():
            try:
                new_date = QDate()
                if '/' in due_date:
                    parts = due_date.split('/')
                    if len(parts) == 3:
                        month = int(parts[0])
                        day = int(parts[1])
                        year = int(parts[2])
                        
                        if year < 100:
                            year = 2000 + year
                        new_date = QDate(year, month, day)
                        
                if not new_date.isValid():
                    date_obj = QDate.fromString(due_date, "MM/dd/yy")
                    if date_obj.isValid():
                        correct_year = 2000 + (date_obj.year() % 100)
                        new_date = QDate(correct_year, date_obj.month(), date_obj.day())
                if new_date.isValid():
                    self.fields["Due Date"].setDate(new_date)
            except Exception as e:
                print(f"Error parsing due date '{due_date}': {e}")
        
        self.fields["Discounted Total"].setText(values[6])
        self.fields["Total Amount"].setText(values[7])

        # Track empty date fields for highlighting
        self.empty_date_fields = set()
        if not values[3].strip():
            self.empty_date_fields.add("Invoice Date")
        if not values[5].strip():
            self.empty_date_fields.add("Due Date")

        self._highlight_empty_fields()

        # Update navigation buttons and list selection
        self.prev_button.setDisabled(index == 0)
        self.next_button.setDisabled(index == len(self.pdf_paths) - 1)
        if self.file_list.currentRow() != index:
            self.file_list.blockSignals(True)
            self.file_list.setCurrentRow(index)
            self.file_list.blockSignals(False)

        # Replace PDF viewer
        new_viewer = InteractivePDFViewer(self.pdf_paths[index])
        index_in_splitter = self.splitter.indexOf(self.viewer)
        self.splitter.replaceWidget(index_in_splitter, new_viewer)
        new_viewer.show()
        self.viewer.deleteLater()
        self.viewer = new_viewer
        # Reapply splitter sizing so the viewer remains visible
        self.splitter.setStretchFactor(index_in_splitter, 1)
        self.splitter.setSizes([150, 350, 550])

    def switch_to_index(self, index):
        """Switch to the selected file from the list."""
        if index < 0 or index >= len(self.pdf_paths):
            return
        if index == self.current_index:
            return
        self.save_current_invoice()
        self.load_invoice(index)

    def show_prev(self):
        if self.current_index > 0:
            self.save_current_invoice()
            self.load_invoice(self.current_index - 1)

    def show_next(self):
        if self.current_index < len(self.pdf_paths) - 1:
            self.save_current_invoice()
            self.load_invoice(self.current_index + 1)

    def on_save(self):
        self.save_current_invoice()
        self.save_changes = True
        self.accept()

    def mark_file_viewed(self, index):
        """Track and visually mark a file as viewed."""
        if index in self.viewed_files:
            return
        self.viewed_files.add(index)
        item = self.file_list.item(index)
        if item is not None:
            item.setForeground(QBrush(Qt.gray))

    def _on_date_changed(self, label):
        """Handle updates to date fields."""
        self._clear_date_highlight(label)

    def load_vendors(self):
        """Load vendors into the combo box."""
        vendors = get_vendor_list()
        if vendors:
            # Sort alphabetically
            vendors.sort()
            self.vendor_combo.clear()
            self.vendor_combo.addItems(vendors)

    def add_new_vendor(self):
        """Open dialog to add a new vendor."""
        dialog = VendorDialog(self)
        if dialog.exec_() == QDialog.Accepted:
            new_vendor = dialog.get_name()
            if new_vendor:
                # Add to combo and select it
                self.vendor_combo.addItem(new_vendor)
                self.vendor_combo.setCurrentText(new_vendor)

    def calculate_due_date(self):
        """Calculate due date from discount terms and invoice date."""
        terms = self.fields["Discount Terms"].text().strip()
        invoice_date = self.fields["Invoice Date"].date().toString("yyyy-MM-dd")
        
        if not terms or not invoice_date:
            QMessageBox.warning(self, "Missing Data", 
                "Please enter both Discount Terms and Invoice Date.")
            return
            
        try:
            due_date = calculate_discount_due_date(terms, invoice_date)
            if due_date:
                # Convert MM/DD/YY to QDate
                month, day, year = due_date.split('/')
                if len(year) == 2:
                    year = "20" + year  # Convert YY to YYYY
                qdate = QDate(int(year), int(month), int(day))
                self.fields["Due Date"].setDate(qdate)
            else:
                QMessageBox.warning(self, "Calculation Error", 
                    "Could not determine due date from the provided terms.")
        except Exception as e:
            QMessageBox.warning(self, "Calculation Error", 
                f"Could not calculate due date: {str(e)}")

    def calculate_discounted_total(self):
        """Calculate discounted total from terms and total amount."""
        terms = self.fields["Discount Terms"].text().strip()
        total = self.fields["Total Amount"].text().strip()
        vendor = self.vendor_combo.currentText()
        
        if not terms or not total:
            QMessageBox.warning(self, "Missing Data", 
                "Please enter both Discount Terms and Total Amount.")
            return
            
        try:
            discounted = calculate_discounted_total(terms, total, vendor)
            if discounted:
                self.fields["Discounted Total"].setText(f"***  {discounted}  ***")
            else:
                QMessageBox.warning(self, "No Discount", 
                    "No discount percentage found in the terms.")
        except Exception as e:
            QMessageBox.warning(self, "Calculation Error",
                f"Could not calculate discounted total: {str(e)}")

    def _clear_date_highlight(self, label):
        """Remove highlight from a date field once the user sets a value."""
        if label in self.empty_date_fields:
            self.empty_date_fields.remove(label)
            self._highlight_empty_fields()

    def _highlight_empty_fields(self):
        """Highlight fields with empty values in yellow."""
        for label, widget in self.fields.items():
            if isinstance(widget, QLineEdit):
                empty = not widget.text().strip()
            elif isinstance(widget, QComboBox):
                empty = not widget.currentText().strip()
            elif isinstance(widget, QDateEdit):
                empty = label in self.empty_date_fields
            else:
                empty = False
            widget.setStyleSheet("background-color: yellow;" if empty else "")

    def get_data(self):
        """Return the entered data as a list in the correct order."""
        data = []
        for label in [
            "Vendor Name", "Invoice Number", "PO Number", "Invoice Date",
            "Discount Terms", "Due Date", "Discounted Total", "Total Amount",
        ]:
            widget = self.fields[label]
            if isinstance(widget, QDateEdit):
                # Format as MM/DD/YY for consistency with main window
                value = widget.date().toString("MM/dd/yy")
            elif isinstance(widget, QComboBox):
                value = widget.currentText().strip()
            else:
                value = widget.text().strip()
            data.append(value)
        return data
    
    def get_all_data(self):
        """Return data for all files after ensuring current edits are saved."""
        self.save_current_invoice()
        return self.values_list