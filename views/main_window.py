"""Main application window for invoice processing."""
import os
import subprocess
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QAbstractItemView, QMessageBox
)
from PyQt5.QtGui import QFont, QColor, QBrush
from PyQt5.QtCore import Qt

from pdf_reader import extract_text_data_from_pdfs
from extractor import extract_fields
from utils import write_to_csv
from assets.constants import COLORS
from views.date_selection import DateDelegate
from views.vendor_dialog import VendorSelectDialog

class InvoiceApp(QWidget):
    """Main application window for invoice processing."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Invoice Extraction App")
        self.setGeometry(100, 100, 1200, 600)

        # --- Main layout setup ---
        self.layout = QVBoxLayout()
        self.label = QLabel("Drop PDF files here or click 'Browse Files'")
        self.label.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(self.label)

        self.browse_button = QPushButton("Browse Files")
        self.browse_button.clicked.connect(self.browse_files)
        self.layout.addWidget(self.browse_button)

        self.setup_table()
        self.layout.addWidget(self.table)

        self.export_button = QPushButton("Export to CSV")
        self.export_button.clicked.connect(self.export_to_csv)
        self.layout.addWidget(self.export_button)

        self.setLayout(self.layout)
        self.setAcceptDrops(True)
        self.loaded_files = set()
        self.original_values = {}  # (row, col): value
        self.manually_edited = set()  # Track (row, col) of manually edited cells

    def setup_table(self):
        """Set up the data table."""
        self.table = QTableWidget()
        self.table.setColumnCount(9)
        self.table.setHorizontalHeaderLabels([
            "Vendor Name", "Invoice Number", "Invoice Date",
            "Discount Terms", "Disc. Due Date",  # Abbreviated
            "Discounted Total", "Total Amount",
            "Source File", "Delete"
        ])
        # Set column widths
        self.table.setColumnWidth(0, 140)  # Vendor Name
        self.table.setColumnWidth(1, 110)  # Invoice Number
        self.table.setColumnWidth(2, 100)  # Invoice Date
        self.table.setColumnWidth(3, 110)  # Discount Terms
        self.table.setColumnWidth(4, 110)  # Disc. Due Date
        self.table.setColumnWidth(5, 120)  # Discounted Total
        self.table.setColumnWidth(6, 100)  # Total Amount
        self.table.setColumnWidth(7, 120)  # Source File
        self.table.setColumnWidth(8, 60)   # Delete

        self.table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.table.cellClicked.connect(self.handle_table_click)
        
        # Set date delegate for date columns
        self.date_delegate = DateDelegate(self.table)
        self.table.setItemDelegateForColumn(2, self.date_delegate)  # Invoice Date
        self.table.setItemDelegateForColumn(4, self.date_delegate)  # Discount Due Date

        # After setting up table:
        self.table.cellChanged.connect(self.handle_cell_changed)

    # --- File browsing ---
    def browse_files(self):
        """Open file dialog to select PDF files."""
        files, _ = QFileDialog.getOpenFileNames(self, "Select PDF files", "", "PDF Files (*.pdf)")
        if files:
            self.process_files(files)

    def dragEnterEvent(self, event):
        """Handle drag enter events."""
        if event.mimeData().hasUrls():
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event):
        """Handle drop events."""
        files = [url.toLocalFile() for url in event.mimeData().urls()]
        pdf_files = [f for f in files if f.lower().endswith(".pdf")]
        if pdf_files:
            self.process_files(pdf_files)

    # --- Main PDF processing logic ---
    def process_files(self, pdf_paths):
        """Process PDF files and add them to the table."""
        new_files = self.filter_new_files(pdf_paths)
        if not new_files:
            print("[INFO] No new files to process.")
            return

        print(f"[INFO] Processing {len(new_files)} new files...")
        self.loaded_files.update(new_files)
        
        self.process_and_add_rows(new_files)
        
    def filter_new_files(self, files):
        """Filter out already processed files."""
        return [f for f in files if f not in self.loaded_files]
        
    def process_and_add_rows(self, files):
        """Process files and add rows to the table."""
        text_blocks = extract_text_data_from_pdfs(files)
        extracted_data = extract_fields(text_blocks)
        
        for row_data, file_path in zip(extracted_data, files):
            self.add_row(row_data, file_path)

    # --- Populate table row ---
    def add_row(self, row_data, file_path):
        """Add a new row to the table."""
        row_position = self.table.rowCount()
        self.table.insertRow(row_position)

        # Check if this file had no OCR words
        is_no_ocr = all((not value or value == "") for value in row_data[:7])

        # Add each cell in the row
        self.populate_row_cells(row_position, row_data, is_no_ocr)
        
        # Add source file and delete columns
        self.add_source_file_cell(row_position, file_path)
        self.add_delete_cell(row_position)
        
        # Track original values
        self.store_original_values(row_position, row_data)
        
        # Highlight row based on content
        self.highlight_row(row_position, is_no_ocr)
        
        # Auto-size vendor column
        self.resize_vendor_column()

    def populate_row_cells(self, row_position, row_data, is_no_ocr):
        """Populate the cells of a row with data."""
        for col, value in enumerate(row_data):
            if col == 0 and not value:
                item = QTableWidgetItem("ADD VENDOR")
                item.setForeground(QBrush(QColor("blue")))
                item.setBackground(QBrush(QColor(COLORS['RED'])))
                font = QFont()
                font.setBold(True)
                font.setUnderline(True)
                item.setFont(font)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            else:
                item = QTableWidgetItem(str(value) if value is not None else "")
            self.table.setItem(row_position, col, item)

    def add_source_file_cell(self, row_position, file_path):
        """Add the source file cell with a clickable link."""
        file_item = QTableWidgetItem(os.path.basename(file_path))
        file_item.setToolTip(file_path)
        file_item.setData(Qt.UserRole, file_path)
        file_item.setFlags(file_item.flags() ^ Qt.ItemIsEditable)
        file_item.setForeground(QColor("blue"))
        file_item.setBackground(QColor(COLORS['LIGHT_GREY']))
        font = QFont()
        font.setUnderline(True)
        file_item.setFont(font)
        self.table.setItem(row_position, 7, file_item)

    def add_delete_cell(self, row_position):
        """Add the delete cell with a delete icon."""
        delete_item = QTableWidgetItem("❌")
        delete_item.setTextAlignment(Qt.AlignCenter)
        delete_item.setFlags(Qt.ItemIsEnabled)
        delete_item.setBackground(QColor(COLORS['LIGHT_GREY']))
        self.table.setItem(row_position, 8, delete_item)

    def store_original_values(self, row_position, row_data):
        """Store the original values of the row for tracking changes."""
        for col, value in enumerate(row_data):
            self.original_values[(row_position, col)] = str(value) if value is not None else ""

    def highlight_row(self, row_position, is_no_ocr):
        """Highlight the row based on its content."""
        empty_count = sum(
            1 for col in range(7)
            if not self.table.item(row_position, col).text().strip()
            or self.table.item(row_position, col).text().strip().upper() == "ADD VENDOR"
        )

        # Highlight the row based on conditions
        for col in range(7):
            current_item = self.table.item(row_position, col)
            if is_no_ocr:
                current_item.setBackground(QColor(COLORS['RED']))  # red for no OCR
            elif current_item.text().strip().upper() == "ADD VENDOR":
                current_item.setBackground(QColor(COLORS['RED']))  # red for ADD VENDOR
            elif empty_count >= 1:
                current_item.setBackground(QColor(COLORS['YELLOW']))  # yellow for incomplete
            else:
                current_item.setBackground(QColor(COLORS['GREEN']))  # green for complete

        if empty_count >= 1:
            print(f"[WARN] Row {row_position + 1} flagged for having {empty_count} empty fields.")

    def resize_vendor_column(self):
        """Auto-resize the vendor column based on content."""
        vendor_col = 0
        self.table.resizeColumnToContents(vendor_col)
        current_width = self.table.columnWidth(vendor_col)
        self.table.setColumnWidth(vendor_col, current_width + 50)

    def handle_cell_changed(self, row, col):
        """Handle when a cell's content is changed by the user."""
        # Only track editable columns (0-6)
        if col > 6:
            return
            
        item = self.table.item(row, col)
        if not item:
            return
            
        # Check if cell was cleared (empty)
        if not item.text().strip():
            # Restore original value
            original_value = self.original_values.get((row, col), "")
            # Temporarily disconnect to avoid recursion
            self.table.cellChanged.disconnect(self.handle_cell_changed)
            item.setText(original_value)
            self.table.cellChanged.connect(self.handle_cell_changed)
            # Remove from manually edited if it matches original
            if (row, col) in self.manually_edited:
                self.manually_edited.remove((row, col))
        else:
            # Check if value is different from original
            original_value = self.original_values.get((row, col), "")
            current_value = item.text().strip()
            
            if current_value != original_value:
                # Mark as manually edited
                self.manually_edited.add((row, col))
                # Set blue background for manually edited cells
                item.setBackground(QColor(COLORS['LIGHT_BLUE']))
            else:
                # Value matches original, remove from manually edited
                if (row, col) in self.manually_edited:
                    self.manually_edited.remove((row, col))
                    
        self.rehighlight_row(row)

    def restore_original_color(self, row, col):
        """Restore the original color of a cell based on content state."""
        item = self.table.item(row, col)
        if not item:
            return
        
        # Always keep manually edited cells blue
        if (row, col) in self.manually_edited:
            item.setBackground(QColor(COLORS['LIGHT_BLUE']))
            return
            
        # Find empty/"ADD VENDOR" cells in editable columns
        empty_cells = [
            c for c in range(7)
            if (
                not self.table.item(row, c) or
                not self.table.item(row, c).text().strip() or
                self.table.item(row, c).text().strip().upper() == "ADD VENDOR"
            )
        ]
        row_is_full = len(empty_cells) == 0
        if item.text().strip().upper() == "ADD VENDOR":
            item.setBackground(QColor(COLORS['RED']))  # red
        elif row_is_full:
            item.setBackground(QColor(COLORS['GREEN']))  # green for complete
        else:
            item.setBackground(QColor(COLORS['YELLOW']))  # yellow for missing

    def rehighlight_row(self, row):
        """Rehighlight a row after changes."""
        # Temporarily disconnect to avoid recursion
        self.table.cellChanged.disconnect(self.handle_cell_changed)
        
        try:
            for col in range(7):
                color = self.determine_cell_color(row, col)
                self.set_cell_color(row, col, color)
        finally:
            # Reconnect the signal after all changes are done
            self.table.cellChanged.connect(self.handle_cell_changed)

    # --- Cell click handling ---
    def handle_table_click(self, row, col):
        """Handle clicks on table cells."""
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
            if value.strip().upper() == "ADD VENDOR":
                self.open_vendor_dialog(row, col)

    # --- Vendor input dialog ---
    def open_vendor_dialog(self, row, col):
        """Open dialog for vendor selection."""
        file_item = self.table.item(row, 7)
        file_path = file_item.toolTip() if file_item else ""

        dialog = VendorSelectDialog(file_path, self)
        if dialog.exec_() == QDialog.Accepted:
            vendor_name = dialog.selected_vendor().strip()
            item = QTableWidgetItem(vendor_name)
            self.table.setItem(row, col, item)

    # --- Export to CSV ---
    def export_to_csv(self):
        """Export table data to CSV file."""
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

    # --- Helper methods for cell handling ---
    def is_cell_empty(self, row, col):
        """Check if a cell is empty or doesn't exist."""
        item = self.table.item(row, col)
        return not item or not item.text().strip()

    def is_add_vendor_cell(self, row, col):
        """Check if a cell contains 'ADD VENDOR'."""
        item = self.table.item(row, col)
        return item and item.text().strip().upper() == "ADD VENDOR"

    def get_cell_text(self, row, col):
        """Safely get cell text or empty string."""
        item = self.table.item(row, col)
        return item.text().strip() if item else ""

    def is_row_no_ocr(self, row):
        """Check if a row has no OCR content (all empty or ADD VENDOR)."""
        for col in range(7):
            text = self.get_cell_text(row, col)
            if text and text.upper() != "ADD VENDOR":
                return False
        return True

    def count_empty_cells(self, row):
        """Count empty cells in a row."""
        count = 0
        for col in range(7):
            if self.is_cell_empty(row, col) or self.is_add_vendor_cell(row, col):
                count += 1
        return count

    def is_row_complete(self, row):
        """Check if a row has all fields filled in."""
        return self.count_empty_cells(row) == 0

    def set_cell_color(self, row, col, color):
        """Set the background color of a cell."""
        item = self.table.item(row, col)
        if item:
            item.setBackground(QColor(color))

    def determine_cell_color(self, row, col):
        """Determine the appropriate color for a cell based on conditions."""
        # Priority order matters here
        if self.is_add_vendor_cell(row, col):
            return COLORS['RED']
        elif (row, col) in self.manually_edited:
            return COLORS['LIGHT_BLUE']
        elif self.is_row_no_ocr(row):
            return COLORS['RED']
        elif self.is_row_complete(row):
            return COLORS['GREEN']
        else:
            return COLORS['YELLOW']