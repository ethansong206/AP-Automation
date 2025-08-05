from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QDateEdit,
    QPushButton, QDialogButtonBox, QSplitter, QWidget, QFormLayout
)
from PyQt5.QtCore import Qt, QDate
from views.pdf_viewer import InteractivePDFViewer

class ManualEntryDialog(QDialog):
    """Dialog for manual entry of invoice fields with PDF viewer."""
    def __init__(self, pdf_path, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Manual Entry")
        self.setMinimumSize(900, 600)

        # --- Left: Form fields ---
        form_layout = QFormLayout()
        self.fields = {}

        # Define all fields you want to collect
        field_names = [
            ("Vendor Name", QLineEdit),
            ("Invoice Number", QLineEdit),
            ("PO Number", QLineEdit),
            ("Invoice Date", QDateEdit),
            ("Discount Terms", QLineEdit),
            ("Due Date", QDateEdit),
            ("Discounted Total", QLineEdit),
            ("Total Amount", QLineEdit),
        ]

        for label, widget_cls in field_names:
            if widget_cls == QDateEdit:
                widget = QDateEdit()
                widget.setCalendarPopup(True)
                widget.setDisplayFormat("yyyy-MM-dd")
                widget.setDate(QDate.currentDate())
            else:
                widget = widget_cls()
            self.fields[label] = widget
            form_layout.addRow(QLabel(label + ":"), widget)

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

    def get_data(self):
        """Return the entered data as a list in the correct order."""
        data = []
        for label in [
            "Vendor Name", "Invoice Number", "PO Number", "Invoice Date",
            "Discount Terms", "Due Date", "Discounted Total", "Total Amount"
        ]:
            widget = self.fields[label]
            if isinstance(widget, QDateEdit):
                value = widget.date().toString("yyyy-MM-dd")
            else:
                value = widget.text().strip()
            data.append(value)
        return data