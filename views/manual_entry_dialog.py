from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QDateEdit,
    QPushButton, QDialogButtonBox, QSplitter, QWidget, QFormLayout,
    QComboBox, QMessageBox
)
from PyQt5.QtCore import Qt, QDate
from views.pdf_viewer import InteractivePDFViewer
from views.vendor_dialog import VendorDialog
from extractors.utils import get_vendor_list, calculate_discount_due_date, calculate_discounted_total

class ManualEntryDialog(QDialog):
    """Dialog for manual entry of invoice fields with PDF viewer."""
    def __init__(self, pdf_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manual Entry")
        self.setMinimumSize(900, 600)

        # --- Left: Form fields ---
        form_layout = QFormLayout()
        self.fields = {}

        # 1. Replace Vendor Name with dropdown + button
        vendor_layout = QHBoxLayout()
        self.vendor_combo = QComboBox()
        self.load_vendors()
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

        left_widget = QWidget()
        left_widget.setLayout(form_layout)

        # --- Right: PDF Viewer ---
        viewer = InteractivePDFViewer(pdf_path)

        # --- Splitter Layout ---
        splitter = QSplitter()
        splitter.addWidget(left_widget)
        splitter.addWidget(viewer)
        splitter.setSizes([350, 550])

        # --- Dialog Buttons ---
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # --- Main Layout ---
        main_layout = QVBoxLayout()
        main_layout.addWidget(splitter)
        main_layout.addWidget(button_box)
        self.setLayout(main_layout)

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

    def get_data(self):
        """Return the entered data as a list in the correct order."""
        data = []
        for label in [
            "Vendor Name", "Invoice Number", "PO Number", "Invoice Date",
            "Discount Terms", "Due Date", "Discounted Total", "Total Amount"
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