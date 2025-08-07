"""Main application window for invoice processing."""
import os
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QHBoxLayout, QDialog, QTableWidgetItem
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt

from views.components.invoice_table import InvoiceTable
from views.components.drop_area import FileDropArea
from views.helpers.style_loader import load_stylesheet, get_style_path
from views.dialogs.vendor_dialog import VendorDialog
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
        title_label = QLabel("GOPC Invoice App")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            font-family: 'Segoe UI', Arial, sans-serif;
            font-size: 24px;
            font-weight: bold;
            color: #2E7D32;
            padding: 10px;
            margin-bottom: 10px;
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
        self.table.vendor_add_clicked.connect(self.open_vendor_dialog)
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
        # Check if this was the discount terms column (4)
        if col == 4:
            self.invoice_controller.recalculate_dependent_fields(row)
    
    # --- UI Action methods ---
    def open_file(self, file_path):
        """Open a file with the system's default application."""
        self.file_controller.open_file(file_path)
    
    def open_vendor_dialog(self, row, col):
        """Open dialog for vendor selection."""
        file_path = self.table.get_file_path_for_row(row)

        dialog = VendorDialog(file_path, self)
        if dialog.exec_() == QDialog.Accepted:
            vendor_name = dialog.selected_vendor().strip()
            self.table.setItem(row, col, QTableWidgetItem(vendor_name))
            
            # Recalculate fields that may depend on vendor
            self.invoice_controller.recalculate_dependent_fields(row)

    def open_manual_entry_dialog(self, row, button=None):
        """Open the manual entry dialog."""
        file_path = self.table.get_file_path_for_row(row)
        
        # Create a list of existing values to pre-populate the dialog
        existing_values = []
        for col in range(8):  # First 8 columns contain the invoice data
            existing_values.append(self.table.get_cell_text(row, col))
        
        # Create dialog with file path and pre-populate with existing values
        dialog = ManualEntryDialog(file_path, self, existing_values)

        if dialog.exec_() == QDialog.Accepted:
            data = dialog.get_data()
            
            # First, update all the table cells with new values
            for col, value in enumerate(data):
                str_value = str(value) if value is not None else ""
                self.table.setItem(row, col, QTableWidgetItem(str_value))
                
                # Mark as edited if different from original - BUT NOT THE DUE DATE COLUMN (5)
                original_value = self.table.original_values.get((row, col), "")
                if str_value != original_value and col != 5:  # Skip marking due date as manually edited
                    self.table.manually_edited.add((row, col))
            
            # Make sure the due date column is NOT in manually_edited
            for r, c in list(self.table.manually_edited):
                if r == row and c == 5:  # Remove due date from manually edited
                    self.table.manually_edited.remove((r, c))
            
            # Make sure to add source file cell if it doesn't exist
            if file_path and not self.table.item(row, 8):
                self.table.add_source_file_cell(row, file_path)
            
            # Make sure to add delete cell if it doesn't exist
            if not self.table.item(row, 9):
                self.table.add_delete_cell(row)
            
            # Add to loaded_files to prevent reprocessing
            if file_path:
                self.file_controller.loaded_files.add(file_path)
            
            # Update row coloring
            self.table.highlight_row(row, is_no_ocr=False)
            
            # Always explicitly recalculate fields when saving from dialog
            self.invoice_controller.recalculate_dependent_fields(row)
            
            # Only AFTER recalculation, update the original_values to match new values
            # BUT DON'T UPDATE DUE DATE - let it always be calculated
            for col, value in enumerate(data):
                if col != 5:  # Skip updating original value for due date
                    str_value = str(value) if value is not None else ""
                    self.table.original_values[(row, col)] = str_value
            
            # For due date, always use the calculated value as original
            due_date_item = self.table.item(row, 5)
            if due_date_item:
                self.table.original_values[(row, 5)] = due_date_item.text()
                
            # Update totals
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
            amount = self.table.get_cell_text(row, 6)
            
            # If no discounted total, use regular total
            if not amount:
                amount = self.table.get_cell_text(row, 7)
                
            # Clean amount string and convert to float
            if amount:
                try:
                    # Remove stars and other formatting
                    amount = amount.replace("*", "").strip()
                    total += float(amount)
                except ValueError:
                    pass
                
        self.total_label.setText(f"Total Amount: ${total:,.2f}")

    # --- Export functionality ---
    def export_to_csv(self):
        """Export table data to CSV file in the accounting system format."""
        # Check if there's data to export
        if self.table.rowCount() == 0:
            QMessageBox.warning(self, "No Data", "There is no data to export.")
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

        success, message = self.invoice_controller.export_to_csv(filename)
        if success:
            QMessageBox.information(self, "Export Successful", f"Data successfully exported to:\n{filename}")
            print(f"[INFO] {message}")
        else:
            QMessageBox.critical(self, "Export Failed", f"Error: {message}")
            print(f"[ERROR] Failed to export: {message}")

    def handle_files_selected(self, files):
        """Handle files selected from drop area."""
        if not files:  # Empty list means browse button was clicked
            self.browse_files()
        else:
            self.process_files(files)