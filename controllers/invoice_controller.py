"""Controller for invoice data operations."""
import re
from datetime import datetime
import csv

from PyQt5.QtWidgets import QMessageBox, QTableWidgetItem
from utils import get_vendor_csv_path

class InvoiceController:
    """Controller for invoice data operations."""
    
    def __init__(self, main_window):
        """Initialize with reference to main window."""
        self.main_window = main_window
    
    def recalculate_dependent_fields(self, row):
        """Recalculate fields that depend on other fields."""
        # First, recalculate the due date from discount terms
        discount_terms = self.main_window.table.get_cell_text(row, 5).strip()
        invoice_date = self.main_window.table.get_cell_text(row, 4).strip()
        
        # Always force recalculation of due date if there are terms and invoice date
        if discount_terms and invoice_date:
            from extractors.utils import calculate_discount_due_date
            try:
                due_date = calculate_discount_due_date(discount_terms, invoice_date)
                if due_date:
                    # FORCE UPDATE: Always update the due date regardless of any tracking state
                    self.main_window.table.update_calculated_field(row, 6, due_date, True)
                    
                    # CRITICAL: Ensure due date is REMOVED from manually_edited
                    key = (row, 6)
                    if key in self.main_window.table.manually_edited:
                        self.main_window.table.manually_edited.remove(key)
            except Exception as e:
                print(f"[WARN] Could not compute due date: {e}")
    
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
            vendors_csv_path = get_vendor_csv_path()
            
            print(f"[DEBUG] Looking for vendors file at: {vendors_csv_path}")
            
            with open(vendors_csv_path, 'r', encoding='utf-8') as file:
                # Use regular CSV reader instead of DictReader
                reader = csv.reader(file)
                for row in reader:
                    if len(row) >= 2:
                        # First column is vendor number, second is vendor name
                        vendor_number = row[0].strip()
                        vendor_name = row[1].strip()
                        if vendor_number and vendor_name:
                            vendor_mapping[vendor_name] = vendor_number
                    
            print(f"[INFO] Loaded {len(vendor_mapping)} vendors from vendors.csv")
        except Exception as e:
            print(f"[ERROR] Failed to load vendor mapping: {e}")
    
        return vendor_mapping
        
    def prepare_export_data(self):
        """Prepare data for export to CSV."""
        table = self.main_window.table
        vendor_mapping = self.load_vendor_mapping()
        rows_to_export = []
        
        # Use the underlying model so filtered-out rows are also exported
        model = getattr(table, "_model", None)
        total_rows = model.rowCount() if model else table.rowCount()

        print(f"[INFO] Preparing export data from {total_rows} rows")

        for src_row in range(total_rows):
            if model:
                vals = model.row_values(src_row)
                raw_vendor_name = vals[0]
                invoice_number = ' '.join((vals[1] or '').strip().split())
                po_number = ' '.join((vals[2] or '').strip().split())
                invoice_date = ' '.join((vals[3] or '').strip().split())
                discount_terms = ' '.join((vals[4] or '').strip().split())
                due_date = ' '.join((vals[5] or '').strip().split())
                total_amount = ' '.join((vals[6] or '').strip().split())
                shipping_cost = ' '.join((vals[7] or '').strip().split())
            else:
                # Fallback to view-access methods
                raw_vendor_name = table.get_cell_text(src_row, 1)
                invoice_number = ' '.join(table.get_cell_text(src_row, 2).strip().split())
                po_number = ' '.join(table.get_cell_text(src_row, 3).strip().split())
                invoice_date = ' '.join(table.get_cell_text(src_row, 4).strip().split())
                discount_terms = ' '.join(table.get_cell_text(src_row, 5).strip().split())
                due_date = ' '.join(table.get_cell_text(src_row, 6).strip().split())
                total_amount = ' '.join(table.get_cell_text(src_row, 7).strip().split())
                shipping_cost = ' '.join(table.get_cell_text(src_row, 8).strip().split())

            vendor_name = ' '.join((raw_vendor_name or '').strip().split())
            
            # Skip incomplete rows
            if not vendor_name or not invoice_number or not invoice_date or not total_amount:
                print(f"[WARN] Skipping incomplete row {src_row+1}")
                continue
        
            # Look up vendor number
            print(f"[DEBUG] Looking up vendor in mapping: '{vendor_name}'")
            vendor_number = vendor_mapping.get(vendor_name, "0")  # Default to "0" if not found
            if not vendor_number or vendor_number == "0":
                print(f"[WARN] No vendor number found for: '{vendor_name}'")
        
            # Create complete data dictionary with all needed information
            invoice_data = {
                "vendor_number": vendor_number,
                "invoice_number": invoice_number,
                "po_number": po_number,
                "invoice_date": self.format_date(invoice_date),
                "discount_terms": discount_terms,
                "due_date": self.format_date(due_date),
                "total_amount": total_amount,
                "shipping_cost": shipping_cost,
                "vendor_name": vendor_name,
            }
            
            rows_to_export.append(invoice_data)
            print(f"[INFO] Prepared row {src_row} for export: {vendor_name} ({vendor_number})")
    
        print(f"[INFO] Export data preparation complete: {len(rows_to_export)} rows")
        return rows_to_export

    def export_to_csv(self, filename):
        """Export prepared data to CSV file."""
        rows_to_export = self.prepare_export_data()
        
        if not rows_to_export:
            print("[WARN] No data to export")
            return False, "No data to export"
            
        try:
            # Import format_and_write_csv (renamed function) to avoid circular imports
            from utils import format_and_write_csv
            success, message = format_and_write_csv(filename, rows_to_export)
            print(f"[INFO] Export completed: {message}")
            return success, message
        except Exception as e:
            error_msg = str(e)
            print(f"[ERROR] Export failed: {error_msg}")
            return False, f"Export failed: {error_msg}"