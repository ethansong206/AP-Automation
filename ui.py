import os
import subprocess
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox,
    QHBoxLayout
)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt
from pdf_reader import extract_text_data_from_pdfs
from extractor import extract_fields
from utils import validate_row_data, write_to_csv

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
        self.table.setColumnCount(9)  # 7 data fields + source file + delete
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

        # Populate data fields
        for col, value in enumerate(row_data):
            item = QTableWidgetItem(str(value) if value is not None else "")
            self.table.setItem(row_position, col, item)

        # Add clickable Source File column
        file_item = QTableWidgetItem(os.path.basename(file_path))
        file_item.setToolTip(file_path)
        file_item.setData(Qt.UserRole, file_path)  # Store full path for later use
        file_item.setFlags(file_item.flags() ^ Qt.ItemIsEditable)
        file_item.setForeground(QColor("blue"))

        font = QFont()
        font.setUnderline(True)
        file_item.setFont(font)

        self.table.setItem(row_position, 7, file_item)

        # Add delete "X" cell
        delete_item = QTableWidgetItem("❌")
        delete_item.setTextAlignment(Qt.AlignCenter)
        delete_item.setFlags(Qt.ItemIsEnabled)
        self.table.setItem(row_position, 8, delete_item)

        # Highlight row if validation fails
        if not validate_row_data(row_data):
            for col in range(7):  # Don't highlight file or delete cols
                self.table.item(row_position, col).setBackground(Qt.yellow)
            print(f"[WARN] Row {row_position + 1} flagged for missing or suspicious values.")

    def handle_table_click(self, row, col):
        if col == 7:  # Source File
            file_item = self.table.item(row, col)
            file_path = file_item.toolTip()
            if not os.path.isfile(file_path):
                QMessageBox.warning(self, "File Not Found", f"The file does not exist:\n{file_path}")
                return

            print(f"[INFO] Opening file: {file_path}")
            try:
                if os.name == 'nt':
                    os.startfile(file_path)
                elif os.name == 'posix':
                    subprocess.call(('open', file_path))
                else:
                    subprocess.call(('xdg-open', file_path))
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to open file:\n{e}")

        elif col == 8:  # Delete button
            file_item = self.table.item(row, 7)  # Column with file link
            file_path = file_item.data(Qt.UserRole) if file_item else None

            confirm = QMessageBox.question(
                self,
                "Delete Row",
                f"Are you sure you want to delete row {row + 1}?",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                self.table.removeRow(row)

                if file_path in self.loaded_files:
                    self.loaded_files.remove(file_path)
                    print(f"[DEBUG] Removed '{file_path}' from loaded_files.")

    def export_to_csv(self):
        rows_to_export = []

        for row in range(self.table.rowCount()):
            row_data = []
            for col in range(7):  # Only export data fields
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
