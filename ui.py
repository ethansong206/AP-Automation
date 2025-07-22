import os
import subprocess
import json
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox,
    QHBoxLayout, QInputDialog
)
from PyQt5.QtGui import QFont, QColor, QBrush
from PyQt5.QtCore import Qt
from pdf_reader import extract_text_data_from_pdfs
from extractor import extract_fields
from utils import validate_row_data, write_to_csv
from extractors.vendor_name import save_manual_mapping

class InvoiceApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Invoice Extraction App")
        self.setGeometry(100, 100, 1200, 600)

        self.layout = QVBoxLayout()
        self.label = QLabel("Drop PDF files here or click 'Browse Files'")
        self.label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.label)

        self.browse_button = QPushButton("Browse Files")
        self.browse_button.clicked.connect(self.browse_files)
        self.layout.addWidget(self.browse_button)

        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Vendor Name", "Invoice Number", "Invoice Date",
            "Discount Terms", "Discount Due Date",
            "Discounted Total", "Total Amount",
            "Source File", "Delete"
        ])
        self.table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.table.cellClicked.connect(self.handle_table_click)
        self.layout.addWidget(self.table)

        self.export_button = QPushButton("Export to CSV")
        self.export_button.clicked.connect(self.export_to_csv)
        self.layout.addWidget(self.export_button)

        self.setLayout(self.layout)
        self.setAcceptDrops(True)

        self.loaded_files = set()

    def browse_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Select PDF files", "", "PDF Files (*.pdf)"
        )
        if files:
            self.process_files(files)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        pdf_files = [f for f in files if f.lower().endswith(".pdf")]
        if pdf_files:
            self.process_files(pdf_files)

    def process_files(self, pdf_paths):
        new_files = [f for f in pdf_paths if f not in self.loaded_files]
        if not new_files:
            print("[INFO] No new files to process.")
            return

        print(f"[INFO] Processing {len(new_files)} new files...")
        self.loaded_files.update(new_files)

        text_blocks = extract_text_data_from_pdfs(new_files)
        extracted_data = extract_fields(text_blocks)

        for row_data, file_path in zip(extracted_data, new_files):
            self.add_row(row_data, file_path)

    def add_row(self, row_data, file_path):
        row_position = self.table.rowCount()
        self.table.insertRow(row_position)

        for col, value in enumerate(row_data):
            if col == 0 and not value:
                item = QTableWidgetItem("Add Vendor")
                item.setForeground(QBrush(QColor("white")))
                item.setBackground(QBrush(QColor("red")))
                font = QFont()
                font.setBold(True)
                item.setFont(font)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            else:
                item = QTableWidgetItem(str(value) if value is not None else "")
            self.table.setItem(row_position, col, item)

        # Add clickable Source File column
        file_item = QTableWidgetItem(os.path.basename(file_path))
        file_item.setToolTip(file_path)
        file_item.setData(Qt.UserRole, file_path)
        file_item.setFlags(file_item.flags() ^ Qt.ItemIsEditable)
        file_item.setForeground(QColor("blue"))
        file_item.setBackground(QColor(230, 230, 230))  # light grey
        font = QFont()
        font.setUnderline(True)
        file_item.setFont(font)
        self.table.setItem(row_position, 7, file_item)

        # Add delete "X" cell
        delete_item = QTableWidgetItem("❌")
        delete_item.setTextAlignment(Qt.AlignCenter)
        delete_item.setFlags(Qt.ItemIsEnabled)
        delete_item.setBackground(QColor(230, 230, 230))  # light grey
        self.table.setItem(row_position, 8, delete_item)

        # Highlight row if 4 or more fields are empty (columns 0–6)
        empty_count = sum(
            1 for col in range(7)
            if not self.table.item(row_position, col).text().strip()
            or self.table.item(row_position, col).text() == "Add Vendor"
        )

        for col in range(7):
            current_item = self.table.item(row_position, col)
            if current_item.text() != "Add Vendor":
                if empty_count >= 4:
                    current_item.setBackground(Qt.yellow)
                else:
                    current_item.setBackground(QColor(220, 255, 220))  # light green

        if empty_count >= 4:
            print(f"[WARN] Row {row_position + 1} flagged for having {empty_count} empty fields.")
    
        # Adjust Vendor Name column width to fit content + 100px
        vendor_col = 0
        self.table.resizeColumnToContents(vendor_col)
        current_width = self.table.columnWidth(vendor_col)
        self.table.setColumnWidth(vendor_col, current_width + 50)


    def handle_table_click(self, row, col):
        header = self.table.horizontalHeaderItem(col).text()

        if header == "Source File":
            file_item = self.table.item(row, col)
            file_path = file_item.toolTip()
            if not os.path.isfile(file_path):
                QMessageBox.warning(self, "File Not Found", f"The file does not exist:\n{file_path}")
                return
            try:
                if os.name == 'nt':
                    os.startfile(file_path)
                elif os.name == 'posix':
                    subprocess.call(('open', file_path))
                else:
                    subprocess.call(('xdg-open', file_path))
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open file:\n{e}")

        elif header == "Delete":
            file_item = self.table.item(row, 7)
            file_path = file_item.data(Qt.UserRole) if file_item else None
            confirm = QMessageBox.question(
                self, "Delete Row", f"Are you sure you want to delete row {row + 1}?",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                self.table.removeRow(row)
                if file_path in self.loaded_files:
                    self.loaded_files.remove(file_path)
                    print(f"[DEBUG] Removed '{file_path}' from loaded_files.")

        elif header == "Vendor Name":
            value = self.table.item(row, col).text()
            if value == "Add Vendor":
                self.open_vendor_dialog(row, col)

    def open_vendor_dialog(self, row, col):
        vendor_name, ok1 = QInputDialog.getText(self, "Manual Vendor Entry", "Enter Vendor Name:")
        if not ok1 or not vendor_name.strip():
            return

        identifier, ok2 = QInputDialog.getText(self, "Vendor Identifier", "Enter a unique string from invoice (e.g., routing #):")
        if not ok2 or not identifier.strip():
            return

        save_manual_mapping(identifier.strip().lower(), vendor_name.strip())

        item = QTableWidgetItem(vendor_name.strip())
        self.table.setItem(row, col, item)

        QMessageBox.information(self, "Vendor Saved", f"Future invoices containing '{identifier}' will now match to '{vendor_name}'.")

    def export_to_csv(self):
        rows_to_export = []

        for row in range(self.table.rowCount()):
            row_data = []
            for col in range(7):
                item = self.table.item(row, col)
                row_data.append(item.text() if item else "")
            rows_to_export.append(row_data)

        try:
            write_to_csv("invoice_data.csv", rows_to_export)
            QMessageBox.information(self, "Export Successful", "Data exported to invoice_data.csv")
            print(f"[INFO] Exported {len(rows_to_export)} rows to invoice_data.csv")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Error: {e}")
            print(f"[ERROR] Failed to export: {e}")