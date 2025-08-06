"""Main application window for invoice processing."""
import os
import subprocess
from datetime import datetime
import csv

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog,
    QTableWidget, QTableWidgetItem, QAbstractItemView, 
    QMessageBox, QDialog, QHBoxLayout
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

        # Add total amount display
        self.total_label = QLabel("Total Amount: $0.00")
        self.total_label.setAlignment(Qt.AlignRight)
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        self.total_label.setFont(font)
        self.layout.addWidget(self.total_label)

        # --- Button layout ---
        button_row = QHBoxLayout()
        self.clear_all_button = QPushButton("Clear All")
        self.clear_all_button.clicked.connect(self.clear_all_rows)
        button_row.addWidget(self.clear_all_button)

        # New button to delete selected rows
        self.delete_selected_button = QPushButton("Delete Selected")
        self.delete_selected_button.clicked.connect(self.delete_selected_rows)
        button_row.addWidget(self.delete_selected_button)

        button_row.addStretch()  # Pushes buttons to the left
        self.layout.addLayout(button_row)

        self.setLayout(self.layout)
        self.setAcceptDrops(True)
        self.loaded_files = set()
        self.original_values = {}  # (row, col): value
        self.manually_edited = set()  # Track (row, col) of manually edited cells
        self.auto_calculated = set()  # Track (row, col) of auto-calculated cells

    def setup_table(self):
        """Set up the data table."""
        self.table = QTableWidget()
        self.table.setColumnCount(10)  # Increased from 9 to 10
        self.table.setHorizontalHeaderLabels([
            "Vendor Name", "Invoice Number", "PO Number", "Invoice Date",
            "Discount Terms", "Due Date",
            "Discounted Total", "Total Amount",
            "Source File", "Delete"
        ])
        # Set column widths
        self.table.setColumnWidth(0, 140)  # Vendor Name
        self.table.setColumnWidth(1, 110)  # Invoice Number
        self.table.setColumnWidth(2, 110)  # PO Number
        self.table.setColumnWidth(3, 100)  # Invoice Date
        self.table.setColumnWidth(4, 110)  # Discount Terms
        self.table.setColumnWidth(5, 100)  # Due Date
        self.table.setColumnWidth(6, 120)  # Discounted Total
        self.table.setColumnWidth(7, 100)  # Total Amount
        self.table.setColumnWidth(8, 120)  # Source File
        self.table.setColumnWidth(9, 60)   # Delete

        self.table.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.table.cellClicked.connect(self.handle_table_click)
        
        # Set date delegate for date columns
        self.date_delegate = DateDelegate(self.table)
        self.table.setItemDelegateForColumn(3, self.date_delegate)  # Invoice Date (now column 3)
        self.table.setItemDelegateForColumn(5, self.date_delegate)  # Discount Due Date (now column 5)

        # After setting up table:
        self.table.cellChanged.connect(self.handle_cell_changed)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)

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
        # Normalize paths for comparison
        normalized_loaded = {os.path.normpath(f) for f in self.loaded_files}
        new_files = []
        
        for file in files:
            norm_path = os.path.normpath(file)
            if norm_path not in normalized_loaded:
                new_files.append(file)
        
        return new_files
        
    def process_and_add_rows(self, files):
        """Process files and add rows to the table."""
        text_blocks = extract_text_data_from_pdfs(files)
        extracted_data = extract_fields(text_blocks)
        
        for row_data, file_path in zip(extracted_data, files):
            self.add_row(row_data, file_path)

    # --- Populate table row ---
    def add_row(self, row_data, file_path):
        """Add a new row to the table."""
        # Ensure row_data has at least 9 elements (for Source File column)
        while len(row_data) < 9:
            row_data.append("")
        row_position = self.table.rowCount()
        self.table.insertRow(row_position)

        # Check if this file had no OCR words
        is_no_ocr = all((not value or value == "") for value in row_data[:7])

        # Add each cell in the row
        self.populate_row_cells(row_position, row_data, is_no_ocr, file_path)
        
        # Only add source file cell if not no OCR (so button is not overwritten)
        if not is_no_ocr:
            self.add_source_file_cell(row_position, file_path)
        self.add_delete_cell(row_position)
        
        # Track original values
        self.store_original_values(row_position, row_data)
        
        # Highlight row based on content
        self.highlight_row(row_position, is_no_ocr)
        
        # Auto-size vendor column
        self.resize_vendor_column()

        self.update_total_amount()

    def populate_row_cells(self, row_position, row_data, is_no_ocr, file_path=None):
        """Populate the cells of a row with data."""
        for col, value in enumerate(row_data):
            if col == 8 and is_no_ocr:
                # Show MANUAL ENTRY button for no OCR rows in Source File column
                button = QPushButton("MANUAL ENTRY")
                button.setProperty("file_path", file_path)  # Store the file path on the button
                button.clicked.connect(lambda _, r=row_position, b=button: self.open_manual_entry_dialog(r, b))
                # Style: red background, black bold all-caps text
                button.setStyleSheet("background-color: #FFC0CB; color: black; font-weight: bold; text-transform: uppercase;")
                self.table.setCellWidget(row_position, col, button)
                print(f"[DEBUG] Set MANUAL ENTRY button at row {row_position}, col {col}")
                continue  # Prevents overwriting the button with a QTableWidgetItem
            elif col == 0 and is_no_ocr:
                # For no OCR rows, leave Vendor Name cell empty (no ADD VENDOR)
                self.table.setItem(row_position, col, QTableWidgetItem(""))
            elif col == 0 and not value:
                item = QTableWidgetItem("ADD VENDOR")
                item.setForeground(QBrush(QColor("blue")))
                item.setBackground(QBrush(QColor(COLORS['RED'])))
                font = QFont()
                font.setBold(True)
                font.setUnderline(True)
                item.setFont(font)
                item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                self.table.setItem(row_position, col, item)
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
        self.table.setItem(row_position, 8, file_item)

    def add_delete_cell(self, row_position):
        """Add the delete cell with a delete icon."""
        delete_item = QTableWidgetItem("❌")
        delete_item.setTextAlignment(Qt.AlignCenter)
        delete_item.setFlags(Qt.ItemIsEnabled)
        delete_item.setBackground(QColor(COLORS['LIGHT_GREY']))
        self.table.setItem(row_position, 9, delete_item)

    def store_original_values(self, row_position, row_data):
        """Store the original values of the row for tracking changes."""
        for col, value in enumerate(row_data):
            self.original_values[(row_position, col)] = str(value) if value is not None else ""

    def highlight_row(self, row_position, is_no_ocr):
        """Highlight the row based on its content."""
        empty_count = sum(
            1 for col in range(8)
            if (
                not self.table.item(row_position, col) or
                not self.table.item(row_position, col).text().strip() or
                self.table.item(row_position, col).text().strip().upper() == "ADD VENDOR"
            )
        )

        for col in range(8):
            current_item = self.table.item(row_position, col)
            if not current_item:
                continue  # Skip cells with no QTableWidgetItem (e.g., "Manual Entry" button)

            # Pink for Discount Terms column if it does NOT contain 'NET'
            if col == 4:
                cell_text = current_item.text().strip().upper()
                if "NET" not in cell_text:
                    current_item.setBackground(QColor("#FFC0CB"))  # Pink
                    continue  # Skip all other color logic for this cell

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
        # Only track editable columns (0-7)
        if col > 7: 
            return
            
        item = self.table.item(row, col)
        if not item:
            return
    
        # Temporarily disconnect to prevent recursion during our processing
        self.table.cellChanged.disconnect(self.handle_cell_changed)
    
        try:
            # Check if cell was cleared (empty)
            if not item.text().strip():
                # Restore original value
                original_value = self.original_values.get((row, col), "")
                item.setText(original_value)
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
            
            # If discount terms column changed, recalculate dependent fields
            if col == 4:  # Discount Terms
                self.recalculate_dependent_fields(row)
                    
            self.rehighlight_row(row)
            
        finally:
            # Reconnect the signal after all changes are done
            self.table.cellChanged.connect(self.handle_cell_changed)

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
        # Safely disconnect to avoid recursion
        try:
            self.table.cellChanged.disconnect(self.handle_cell_changed)
            was_connected = True
        except TypeError:
            # Signal was not connected
            was_connected = False
        
        try:
            for col in range(8):
                color = self.determine_cell_color(row, col)
                self.set_cell_color(row, col, color)
        finally:
            # Only reconnect if it was connected before
            if was_connected:
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
            # Get file path from either the Source File cell or the MANUAL ENTRY button
            file_path = None
            
            # Check Source File column first (column 8)
            file_item = self.table.item(row, 8)
            if file_item:
                file_path = file_item.toolTip() or file_item.data(Qt.UserRole)
            
            # If no path found and this is a non-OCR row, check for MANUAL ENTRY button
            if not file_path:
                for col_idx in range(self.table.columnCount()):
                    cell_widget = self.table.cellWidget(row, col_idx)
                    if cell_widget and isinstance(cell_widget, QPushButton) and cell_widget.text() == "MANUAL ENTRY":
                        file_path = cell_widget.property("file_path")
                        break
            
            confirm = QMessageBox.question(
                self, "Delete Row", f"Are you sure you want to delete row {row + 1}?",
                QMessageBox.Yes | QMessageBox.No
            )
            if confirm == QMessageBox.Yes:
                print(f"[DEBUG] Removing file from loaded_files: {file_path}")
                
                # Clean up all data structures that store information about this row
                self.cleanup_row_data(row)
                self.table.removeRow(row)
                
                if file_path and file_path in self.loaded_files:
                    self.loaded_files.remove(file_path)
                self.update_total_amount()
        
        elif header == "Vendor Name":
            value = self.table.item(row, col).text()
            if value.strip().upper() == "ADD VENDOR":
                self.open_vendor_dialog(row, col)

    # --- Vendor input dialog ---
    def open_vendor_dialog(self, row, col):
        """Open dialog for vendor selection."""
        file_item = self.table.item(row, 8)
        file_path = file_item.toolTip() if file_item else ""

        dialog = VendorSelectDialog(file_path, self)
        if dialog.exec_() == QDialog.Accepted:
            vendor_name = dialog.selected_vendor().strip()
            item = QTableWidgetItem(vendor_name)
            self.table.setItem(row, col, item)

    # --- Export to CSV ---
    def export_to_csv(self):
        """Export table data to CSV file in the accounting system format."""
        # First, prepare the data to export
        vendor_mapping = self.load_vendor_mapping()
        rows_to_export = []

        # Check if there's data to export
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "No Data", "There is no data to export.")
            return

        for row in range(self.table.rowCount()):
            # Get data from table cells
            vendor_name = self.get_cell_text(row, 0)
            invoice_number = self.get_cell_text(row, 1)
            po_number = self.get_cell_text(row, 2)
            invoice_date = self.get_cell_text(row, 3)
            discount_terms = self.get_cell_text(row, 4) 
            due_date = self.get_cell_text(row, 5) 
            discounted_total = self.get_cell_text(row, 6)  
            total_amount = self.get_cell_text(row, 7) 
            
            # Skip incomplete rows
            if not vendor_name or not invoice_number or not invoice_date or not total_amount:
                print(f"[WARN] Skipping incomplete row {row+1}")
                continue
                
            # Look up vendor number
            vendor_number = vendor_mapping.get(vendor_name, "")
            if not vendor_number:
                print(f"[WARN] No vendor number found for: {vendor_name}")
                
            # Use discounted total if available, otherwise use regular total
            final_amount = discounted_total if discounted_total else total_amount
            
            # Clean up formatting from amount (remove asterisks and extra spaces)
            final_amount = final_amount.replace("***", "").strip()
            
            # Create row in accounting system format
            accounting_row = [
                vendor_number,                    # VCHR_VEND_NO
                self.format_date(invoice_date),   # VCHR_INVC_DAT
                invoice_number,                   # VCHR_INVC_NO
                vendor_name,                      # VEND_NAM
                self.format_date(due_date),       # DUE_DAT
                po_number,                        # PO_NO (now using actual PO number)
                "0697-099",                       # ACCT_NO (fixed value)
                "0697-099",                       # CP_ACCT_NO (fixed value)
                final_amount                      # AMT
            ]
            
            rows_to_export.append(accounting_row)
        
        # Skip export if no valid rows
        if not rows_to_export:
            QMessageBox.warning(self, "No Valid Data", "No valid rows to export.")
            return
        
        # Open file dialog for user to select destination
        options = QFileDialog.Options()
        default_name = "accounting_import.csv"
        filename, _ = QFileDialog.getSaveFileName(
            self,
            "Export to CSV",
            default_name,
            "CSV Files (*.csv);;All Files (*)",
            options=options
        )
        
        if not filename:  # User canceled
            return
        
        # Ensure .csv extension
        if not filename.lower().endswith('.csv'):
            filename += '.csv'

        try:
            write_to_csv(filename, rows_to_export)
            QMessageBox.information(
                self, 
                "Export Successful", 
                f"Data successfully exported to:\n{filename}"
            )
            print(f"[INFO] Exported {len(rows_to_export)} rows to {filename}")
        except Exception as e:
            QMessageBox.critical(self, "Export Failed", f"Error: {e}")
            print(f"[ERROR] Failed to export: {e}")

    def format_date(self, date_str):
        """Format date for accounting system."""
        if not date_str:
            return ""
        
        try:
            # Try to parse the date
            if "/" in date_str:
                parts = date_str.split("/")
                if len(parts) == 3:
                    return date_str  # Already in MM/DD/YY format
            
            # If not in correct format, try to convert
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            return dt.strftime("%m/%d/%y")
        except:
            return date_str  # Return as-is if parsing fails

    def load_vendor_mapping(self):
        """Load vendor numbers from vendors.csv."""
        vendor_mapping = {}
        
        try:
            # Use resource_path to find the file in PyInstaller bundle
            from utils import resource_path
            vendors_csv_path = resource_path(os.path.join("data", "vendors.csv"))
            
            print(f"[DEBUG] Looking for vendors file at: {vendors_csv_path}")
            
            with open(vendors_csv_path, 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                for row in reader:
                    vendor_number = row.get("Vendor No. (Sage)", "").strip()
                    vendor_name = row.get("Vendor Name", "").strip()
                    if vendor_number and vendor_name:
                        vendor_mapping[vendor_name] = vendor_number
                        
            print(f"[INFO] Loaded {len(vendor_mapping)} vendors from vendors.csv")
        except Exception as e:
            print(f"[ERROR] Failed to load vendor mapping: {e}")
        
        return vendor_mapping

    def update_total_amount(self):
        """Update the total amount display."""
        total = 0.0
        for row in range(self.table.rowCount()):
            amount_item = self.table.item(row, 6)  # Total Amount column
            if amount_item and amount_item.text():
                try:
                    total += float(amount_item.text())
                except ValueError:
                    continue
        self.total_label.setText(f"Total Amount: ${total:,.2f}")

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
        for col in range(8): 
            text = self.get_cell_text(row, col)
            if text and text.upper() != "ADD VENDOR":
                return False
        return True

    def count_empty_cells(self, row):
        """Count empty cells in a row."""
        count = 0
        for col in range(8):
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
        # Pink for Discount Terms column if it does NOT contain 'NET'
        if col == 4:
            cell_text = self.get_cell_text(row, col).upper()
            if "NET" not in cell_text and cell_text:
                return "#FFC0CB"  # Pink

        if self.is_add_vendor_cell(row, col):
            return COLORS['RED']
        elif (row, col) in self.manually_edited:
            return COLORS['LIGHT_BLUE']
        elif (row, col) in self.auto_calculated:
            return COLORS['LIGHT_BLUE']  # Same color for auto-calculated
        elif self.is_row_no_ocr(row):
            return COLORS['RED']
        elif self.is_row_complete(row):
            return COLORS['GREEN']
        else:
            return COLORS['YELLOW']

    def clear_all_rows(self):
        """Clear all rows from the table after confirmation."""
        if self.table.rowCount() == 0:
            return
        confirm = QMessageBox.question(
            self, "Clear All", "Are you sure you want to delete all rows?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            self.table.setRowCount(0)
            self.loaded_files.clear()
            self.original_values.clear()
            self.manually_edited.clear()
            self.auto_calculated.clear()  # Also clear auto-calculated
            self.update_total_amount()

    def delete_selected_rows(self):
        """Delete the selected rows from the table."""
        selected_rows = set(index.row() for index in self.table.selectedIndexes())
        if not selected_rows:
            return
        
        confirm = QMessageBox.question(
            self, "Delete Selected Rows", "Are you sure you want to delete the selected rows?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm == QMessageBox.Yes:
            # Sort rows in descending order to avoid shifting issues
            for row in sorted(selected_rows, reverse=True):
                file_item = self.table.item(row, 8)
                file_path = file_item.data(Qt.UserRole) if file_item else None
                self.table.removeRow(row)
                if file_path in self.loaded_files:
                    self.loaded_files.remove(file_path)
            self.update_total_amount()

    def open_manual_entry_dialog(self, row, button=None):
        """Open the manual entry dialog for a no OCR row."""
        file_path = ""
        if button is not None:
            file_path = button.property("file_path")
        else:
            # fallback: try to get from table item (for other usages)
            file_item = self.table.item(row, 8)
            file_path = file_item.toolTip() if file_item else ""
        
        from views.manual_entry_dialog import ManualEntryDialog
        dialog = ManualEntryDialog(file_path, self)
    
        if dialog.exec_() == QDialog.Accepted:
            # Temporarily disconnect cell change signals
            try:
                self.table.cellChanged.disconnect(self.handle_cell_changed)
                was_connected = True
            except TypeError:
                was_connected = False
            
            try:
                data = dialog.get_data()
            
                # Update the table with the new data
                for col, value in enumerate(data):
                    # Create table item
                    item = QTableWidgetItem(str(value) if value is not None else "")
                    self.table.setItem(row, col, item)
                
                    # Update original values dictionary
                    self.original_values[(row, col)] = str(value) if value is not None else ""
                
                # Make sure to add source file cell if it doesn't exist
                if file_path and not self.table.item(row, 8):
                    self.add_source_file_cell(row, file_path)
                
                # Make sure to add delete cell if it doesn't exist
                if not self.table.item(row, 9):
                    self.add_delete_cell(row)
                
                # Add to loaded_files to prevent reprocessing
                if file_path:
                    self.loaded_files.add(file_path)
                
                # Update row coloring and recalculate fields
                self.highlight_row(row, is_no_ocr=False)
            
                # Recalculate any dependent fields (due date & discount)
                self.recalculate_dependent_fields(row)
                
            finally:
                # Reconnect signals if they were connected
                if was_connected:
                    self.table.cellChanged.connect(self.handle_cell_changed)

    def recalculate_dependent_fields(self, row):
        """Recalculate due date and discounted total when terms change."""
        from extractors.utils import calculate_discount_due_date, calculate_discounted_total
        import re
        
        # Get the required values
        terms = self.get_cell_text(row, 4)
        invoice_date = self.get_cell_text(row, 3)
        total_amount = self.get_cell_text(row, 7)
        vendor_name = self.get_cell_text(row, 0)
        
        # Only proceed if we have valid input data
        if not terms or not invoice_date or not total_amount or vendor_name == "ADD VENDOR":
            return
            
        try:
            # Calculate new due date
            due_date = calculate_discount_due_date(terms, invoice_date)
            if due_date:
                # Update due date cell
                due_date_item = QTableWidgetItem(due_date)
                due_date_item.setBackground(QColor(COLORS['LIGHT_BLUE']))
                
                # Add a visual indicator that this is calculated
                font = due_date_item.font()
                font.setItalic(True)
                due_date_item.setFont(font)
                
                self.table.setItem(row, 5, due_date_item)
                # Track as auto-calculated
                self.auto_calculated.add((row, 5))
        
            # Check if terms contains a percentage
            has_discount = re.search(r"(\d+)%", terms) is not None
            special_vendors = ["TOPO ATHLETIC", "Ruffwear", "ON Running", "Free Fly Apparel", 
                               "Hadley Wren", "Gregory Mountain Products"]
            is_special_vendor = vendor_name in special_vendors
            
            if not has_discount and not is_special_vendor:
                # No discount percentage found, clear the discounted total
                empty_item = QTableWidgetItem("")
                self.table.setItem(row, 6, empty_item)
                # Remove from auto-calculated if it was there
                if (row, 6) in self.auto_calculated:
                    self.auto_calculated.remove((row, 6))
            else:
                # Calculate discounted total - Handle None case
                discounted_total = calculate_discounted_total(terms, total_amount, vendor_name)
                if discounted_total is not None and discounted_total:  # Check for None and empty string
                    # Update discounted total cell with visual distinction
                    disc_total_item = QTableWidgetItem(f"***  {discounted_total}  ***")
                    disc_total_item.setBackground(QColor(COLORS['LIGHT_BLUE']))
                    
                    # Add a visual indicator that this is calculated
                    font = disc_total_item.font()
                    font.setItalic(True)
                    disc_total_item.setFont(font)
                    
                    self.table.setItem(row, 6, disc_total_item)
                    # Track as auto-calculated
                    self.auto_calculated.add((row, 6))
                
        except Exception as e:
            # Handle calculation errors with user feedback
            print(f"[ERROR] Calculation failed: {e}")
            # Optional: Display a message to the user
            QMessageBox.warning(
                self, 
                "Calculation Error", 
                f"Could not recalculate fields from terms: {terms}\nError: {str(e)}"
            )

    def cleanup_row_data(self, row):
        """Clean up all data associated with a row."""
        # Remove from original_values
        keys_to_remove = [key for key in self.original_values if key[0] == row]
        for key in keys_to_remove:
            del self.original_values[key]
    
        # Remove from manually_edited
        keys_to_remove = [(r, c) for r, c in self.manually_edited if r == row]
        for key in keys_to_remove:
            self.manually_edited.remove(key)
        
        # Remove from auto_calculated
        keys_to_remove = [(r, c) for r, c in self.auto_calculated if r == row]
        for key in keys_to_remove:
            self.auto_calculated.remove(key)
        
        # Also reindex the remaining data for rows after this one
        def reindex_dict_keys(data_dict, deleted_row):
            new_dict = {}
            for (r, c), value in data_dict.items():
                if r > deleted_row:
                    new_dict[(r-1, c)] = value
                elif r < deleted_row:
                    new_dict[(r, c)] = value
            return new_dict
        
        def reindex_set_keys(data_set, deleted_row):
            new_set = set()
            for r, c in data_set:
                if r > deleted_row:
                    new_set.add((r-1, c))
                elif r < deleted_row:
                    new_set.add((r, c))
            return new_set
        
        # Apply reindexing
        self.original_values = reindex_dict_keys(self.original_values, row)
        self.manually_edited = reindex_set_keys(self.manually_edited, row)
        self.auto_calculated = reindex_set_keys(self.auto_calculated, row)