"""Main application window for invoice processing."""
import os
import re
import shutil
from datetime import datetime

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QHBoxLayout, QDialog, QTableWidgetItem
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from views.components.invoice_table import InvoiceTable
from views.components.drop_area import FileDropArea
from views.helpers.style_loader import load_stylesheet, get_style_path
from views.dialogs.manual_entry_dialog import ManualEntryDialog

from controllers.file_controller import FileController
from controllers.invoice_controller import InvoiceController
from models.invoice import Invoice

class InvoiceApp(QWidget):
    """Main application window for invoice processing."""
    
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Invoice Extraction App")
        # Increase width from 1200 to 1300 pixels
        self.setGeometry(100, 100, 1300, 650)  # Width increased to 1300, height to 650
        
        # Apply stylesheet
        stylesheet = load_stylesheet(get_style_path('default.qss'))
        if stylesheet:
            self.setStyleSheet(stylesheet)

        # Create controllers
        self.file_controller = FileController(self)
        self.invoice_controller = InvoiceController(self)
        
        # Set up UI components
        self.setup_ui()
        self.setAcceptDrops(True)

    def setup_ui(self):
        """Set up the main UI components."""
        # --- Main layout setup ---
        self.layout = QVBoxLayout()
        
        # Add title at the top
        title_label = QLabel("GOPC\nInvoice App")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            font-family: 'Montserrat', Arial, sans-serif;
            font-size: 28px;
            font-weight: bold;
            color: #5E6F5E;
            padding: 10px;
            margin-bottom: 8px;
            line-height: 1;
        """)
        self.layout.addWidget(title_label)
        
        # Replace the old label and button with the new drop area
        self.drop_area = FileDropArea()
        self.drop_area.filesSelected.connect(self.handle_files_selected)
        self.layout.addWidget(self.drop_area)
        
        # Table
        self.table = InvoiceTable()
        self.setup_table_connections()
        self.layout.addWidget(self.table)

        # Export button
        self.export_button = QPushButton("Export to CSV")
        self.export_button.setObjectName("exportButton")
        self.export_button.clicked.connect(self.export_to_csv)
        self.layout.addWidget(self.export_button)

        # --- Button layout ---
        button_row = QHBoxLayout()

        # Left side: buttons
        button_group = QHBoxLayout()
        self.clear_all_button = QPushButton("Clear All")
        self.clear_all_button.setObjectName("clearAllButton")
        self.clear_all_button.clicked.connect(self.clear_all_rows)
        button_group.addWidget(self.clear_all_button)

        self.delete_selected_button = QPushButton("Delete Selected")
        self.delete_selected_button.setObjectName("deleteSelectedButton")
        self.delete_selected_button.clicked.connect(self.delete_selected_rows)
        button_group.addWidget(self.delete_selected_button)
        button_row.addLayout(button_group)

        # Export files button between Delete Selected and Total Amount
        self.export_files_button = QPushButton("Export Files to Folder")
        self.export_files_button.setObjectName("exportFilesButton")
        self.export_files_button.clicked.connect(self.export_files_to_folder)
        button_row.addWidget(self.export_files_button)

        # Add stretching space in the middle
        button_row.addStretch()

        # Right side: total amount
        self.total_label = QLabel("Total Amount: $0.00")
        self.total_label.setObjectName("totalLabel")
        self.total_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        font = QFont()
        font.setBold(True)
        font.setPointSize(12)
        self.total_label.setFont(font)
        button_row.addWidget(self.total_label)

        # Add the combined row to the main layout
        self.layout.addLayout(button_row)

        self.setLayout(self.layout)

    def setup_table_connections(self):
        """Set up signal connections for the table."""
        self.table.row_deleted.connect(self.handle_row_deleted)
        self.table.source_file_clicked.connect(self.open_file)
        self.table.manual_entry_clicked.connect(self.open_manual_entry_dialog)
        self.table.cell_manually_edited.connect(self.handle_cell_edited)

    # --- File handling methods ---
    def browse_files(self):
        """Open file dialog to select PDF files."""
        files, _ = QFileDialog.getOpenFileNames(self, "Select PDF files", "", "PDF Files (*.pdf)")
        if files:
            self.process_files(files)

    # --- Main processing logic ---
    def process_files(self, pdf_paths):
        """Process PDF files and add them to the table."""
        data = self.file_controller.process_files(pdf_paths)
        
        if not data:
            return
        
        for extracted_data, file_path in data:
            invoice = Invoice.from_extracted_data(extracted_data, file_path)
            self.table.add_row(invoice.to_row_data(), file_path, invoice.is_no_ocr)
            
        self.update_total_amount()
    
    # --- Event handlers ---
    def handle_row_deleted(self, row, file_path):
        """Handle when a row is deleted from the table."""
        self.file_controller.remove_file(file_path)
        self.update_total_amount()
    
    def handle_cell_edited(self, row, col):
        """Handle when a cell is manually edited."""
        # Check if this was the discount terms column (5)
        if col == 5:
            self.invoice_controller.recalculate_dependent_fields(row)
    
    # --- UI Action methods ---
    def open_file(self, file_path):
        """Open a file with the system's default application."""
        self.file_controller.open_file(file_path)
    
    def open_manual_entry_dialog(self, row, button=None):
        """Open the manual entry dialog for all files starting at a specific row."""
        file_paths = []
        values_list = []
        flag_states = []
        for r in range(self.table.rowCount()):
            file_paths.append(self.table.get_file_path_for_row(r))
            row_values = [self.table.get_cell_text(r, c) for c in range(1, 9)]
            values_list.append(row_values)
            flag_states.append(self.table.is_row_flagged(r))

        dialog = ManualEntryDialog(file_paths, self, values_list, flag_states, start_index=row)
        dialog.file_deleted.connect(self._on_dialog_deleted_file)

        dialog.row_saved.connect(self.on_manual_row_saved)

        if dialog.exec_() == QDialog.Accepted and dialog.save_changes:
            all_data = dialog.get_all_data()
            flag_states = dialog.get_flag_states()

            for path, data in zip(file_paths, all_data):
                row_idx = self.table.find_row_by_file_path(path)
                if row_idx < 0:
                    continue

                for idx, value in enumerate(data):
                    col = idx + 1
                    str_value = str(value) if value is not None else ""

                    existing_item = self.table.item(row_idx, col)
                    original_value = existing_item.data(Qt.UserRole) if existing_item else ""

                    item = QTableWidgetItem(str_value)
                    item.setData(Qt.UserRole, str_value)
                    self.table.setItem(row_idx, col, item)

                    if str_value != original_value and col != 6:
                        self.table.manually_edited.add((row_idx, col))

                for r_edit, c_edit in list(self.table.manually_edited):
                    if r_edit == row_idx and c_edit == 6:
                        self.table.manually_edited.remove((r_edit, c_edit))

                if path and not self.table.item(row_idx, 9):
                    self.table.add_source_file_cell(row_idx, path)

                if not self.table.item(row_idx, 10):
                    self.table.add_delete_cell(row_idx)

                if path:
                    self.file_controller.loaded_files.add(path)

                self.table.highlight_row(row_idx)
                self.invoice_controller.recalculate_dependent_fields(row_idx)

            for path, flagged in zip(file_paths, flag_states):
                row_idx = self.table.find_row_by_file_path(path)
                if row_idx >= 0 and self.table.is_row_flagged(row_idx) != flagged:
                    self.table.toggle_row_flag(row_idx)

            self.update_total_amount()
    
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
            self.table.clear_tracking_data()  # Add this line to clear all tracking data
            self.file_controller.clear_all_files()
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
                file_path = self.table.get_file_path_for_row(row)
                # Clean up tracking data before removing the row
                self.table.cleanup_row_data(row)  
                self.table.removeRow(row)
                self.file_controller.remove_file(file_path)
            self.update_total_amount()
            
    def update_total_amount(self):
        """Update the total amount display."""
        total = 0.0
        for row in range(self.table.rowCount()):
            # Try discounted total first
            amount = self.table.get_cell_text(row, 7)
            
            # If no discounted total, use regular total
            if not amount:
                amount = self.table.get_cell_text(row, 8)
                
            # Clean amount string and convert to float
            if amount:
                try:
                    # Remove stars and other formatting
                    amount = amount.replace("*", "").strip()
                    total += float(amount)
                except ValueError:
                    pass
                
        self.total_label.setText(f"Total Amount: ${total:,.2f}")

    def _on_dialog_deleted_file(self, file_path: str):
        """Remove the row (and let row_deleted signal clean up controller)."""
        if not file_path:
            return
        # No confirm prompt here—the dialog already confirmed.
        self.table.delete_row_by_file_path(file_path, confirm=False)

    def on_manual_row_saved(self, file_path: str, row_values: list, flagged: bool):
        """Update the table row for the given file path with new values and flag state."""
        row = self.table.update_row_by_source(file_path, row_values)
        if row >= 0 and self.table.is_row_flagged(row) != flagged:
            self.table.toggle_row_flag(row)
        self.update_total_amount()

    # --- Export functionality ---
    def export_to_csv(self):
        """Export table data to CSV file in the accounting system format."""
        # Check if there's data to export
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "No Data", "There is no data to export.")
            return
        
        # Open file dialog for user to select destination
        options = QFileDialog.Options() | QFileDialog.DontConfirmOverwrite
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

        success, message = self.invoice_controller.export_to_csv(filename)
        if success:
            QMessageBox.information(self, "Export Successful", message)
            print(f"[INFO] {message}")
        else:
            QMessageBox.critical(self, "Export Failed", f"Error: {message}")
            print(f"[ERROR] Failed to export: {message}")

    def export_files_to_folder(self):
        """Export and organize source PDF files into a user-selected folder."""
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "No Files", "There are no files to export.")
            return

        target_dir = QFileDialog.getExistingDirectory(self, "Select Export Folder")
        if not target_dir:
            return

        # Create month subfolders if they do not exist
        month_names = [
            "Jan", "Feb", "Mar", "Apr", "May", "Jun",
            "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"
        ]
        month_dirs = []
        for i, name in enumerate(month_names, 1):
            month_path = os.path.join(target_dir, f"{i:02d} - {name}")
            if not os.path.exists(month_path):
                os.makedirs(month_path)
            month_dirs.append(month_path)

        for row in range(self.table.rowCount()):
            file_path = self.table.get_file_path_for_row(row)
            if not file_path or not os.path.isfile(file_path):
                continue

            vendor = self._sanitize_filename(self.table.get_cell_text(row, 1)) or "UNKNOWN"
            po_number = self._sanitize_filename(self.table.get_cell_text(row, 3)) or "PO"
            invoice_number = self._sanitize_filename(self.table.get_cell_text(row, 2)) or "INV"

            new_name = f"{vendor}_{po_number}_{invoice_number}.pdf"

            date_str = self.table.get_cell_text(row, 4)
            date_obj = self._parse_invoice_date(date_str)
            if date_obj:
                dest_dir = month_dirs[date_obj.month - 1]
            else:
                dest_dir = target_dir

            dest_path = os.path.join(dest_dir, new_name)
            if os.path.exists(dest_path):
                print(f"[INFO] Skipping existing file: {dest_path}")
                continue

            try:
                shutil.copy2(file_path, dest_path)
            except Exception as e:
                print(f"[ERROR] Failed to copy '{file_path}' to '{dest_path}': {e}")

        QMessageBox.information(self, "Export Complete", f"Files exported to:\n{target_dir}")

    # --- Helper methods ---
    def _sanitize_filename(self, text):
        text = (text or "").strip().replace(" ", "_")
        return re.sub(r"[^A-Za-z0-9_\-]", "", text)

    def _parse_invoice_date(self, date_str):
        for fmt in ("%m/%d/%y", "%m/%d/%Y", "%Y-%m-%d", "%Y/%m/%d"):
            try:
                return datetime.strptime(date_str, fmt)
            except Exception:
                continue
        return None

    def handle_files_selected(self, files):
        """Handle files selected from drop area."""
        if not files:  # Empty list means browse button was clicked
            self.browse_files()
        else:
            self.process_files(files)