"""Controller for invoice data operations."""
import re
from datetime import datetime
import csv
import os

from PyQt5.QtWidgets import QMessageBox, QTableWidgetItem
from utils import resource_path

class InvoiceController:
    """Controller for invoice data operations."""
    
    def __init__(self, main_window):
        """Initialize with reference to main window."""
        self.main_window = main_window
    
    def recalculate_dependent_fields(self, row):
        """Recalculate fields that depend on other fields."""
        # First, recalculate the due date from discount terms
        discount_terms = self.main_window.table.get_cell_text(row, 4).strip()
        invoice_date = self.main_window.table.get_cell_text(row, 3).strip()
        
        # Always force recalculation of due date if there are terms and invoice date
        if discount_terms and invoice_date:
            from extractors.utils import calculate_discount_due_date
            try:
                due_date = calculate_discount_due_date(discount_terms, invoice_date)
                if due_date:
                    # FORCE UPDATE: Always update the due date regardless of any tracking state
                    self.main_window.table.update_calculated_field(row, 5, due_date, True)
                    
                    # CRITICAL: Ensure due date is REMOVED from manually_edited
                    key = (row, 5)
                    if key in self.main_window.table.manually_edited:
                        self.main_window.table.manually_edited.remove(key)
            except Exception as e:
                print(f"[WARN] Could not compute due date: {e}")
        
        # Now calculate the discounted total
        self.recalculate_discounted_total(row)

    def recalculate_discounted_total(self, row):
        """Recalculate due date and discounted total when terms change."""
        from extractors.utils import calculate_discounted_total
        
        table = self.main_window.table
        
        # Get the required values
        terms = table.get_cell_text(row, 4)
        total_amount = table.get_cell_text(row, 7)
        vendor_name = table.get_cell_text(row, 0)
        
        # Only proceed if we have valid input data
        if not terms or not total_amount or not vendor_name:
            return
            
        try:
            # Check if terms contains a percentage
            has_discount = re.search(r"(\d+)%", terms) is not None
            special_vendors = [
                "TOPO ATHLETIC", "Ruffwear", "ON Running", 
                "Free Fly Apparel", "Hadley Wren", "Gregory Mountain Products"
            ]
            is_special_vendor = vendor_name in special_vendors
            
            if not has_discount and not is_special_vendor:
                # No discount percentage found, clear the discounted total
                table.update_calculated_field(row, 6, "", False)
                # Remove from auto-calculated if it was there
                if (row, 6) in table.auto_calculated:
                    table.auto_calculated.remove((row, 6))
            else:
                # Calculate discounted total - Handle None case
                discounted_total = calculate_discounted_total(terms, total_amount, vendor_name)
                if discounted_total is not None and discounted_total:  # Check for None and empty string
                    table.update_calculated_field(row, 6, f"***  {discounted_total}  ***")
                
        except Exception as e:
            # Handle calculation errors with user feedback
            print(f"[ERROR] Calculation failed: {e}")
            QMessageBox.warning(
                self.main_window, 
                "Calculation Error", 
                f"Could not recalculate fields from terms: {terms}\nError: {str(e)}"
            )
    
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
            vendors_csv_path = resource_path(os.path.join("data", "vendors.csv"))
            
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
        
        print(f"[INFO] Preparing export data from {table.rowCount()} rows")
        
        for row in range(table.rowCount()):
            # Get data from table cells and clean thoroughly
            raw_vendor_name = table.get_cell_text(row, 0)
            vendor_name = ' '.join(raw_vendor_name.strip().split())
            
            # Get other invoice data
            invoice_number = ' '.join(table.get_cell_text(row, 1).strip().split())
            po_number = ' '.join(table.get_cell_text(row, 2).strip().split())
            invoice_date = ' '.join(table.get_cell_text(row, 3).strip().split())
            terms = ' '.join(table.get_cell_text(row, 4).strip().split())
            due_date = ' '.join(table.get_cell_text(row, 5).strip().split())
            discounted_total = ' '.join(table.get_cell_text(row, 6).strip().split())
            total_amount = ' '.join(table.get_cell_text(row, 7).strip().split())
            
            # Skip incomplete rows
            if not vendor_name or not invoice_number or not invoice_date or not total_amount:
                print(f"[WARN] Skipping incomplete row {row+1}")
                continue
        
            # Look up vendor number
            print(f"[DEBUG] Looking up vendor in mapping: '{vendor_name}'")
            vendor_number = vendor_mapping.get(vendor_name, "0")  # Default to "0" if not found
            if not vendor_number or vendor_number == "0":
                print(f"[WARN] No vendor number found for: '{vendor_name}'")
        
            # Use discounted total if available, otherwise use regular total
            final_amount = discounted_total if discounted_total else total_amount
            
            # Clean up formatting from amount
            final_amount = final_amount.replace("***", "").strip()
            
            # Create complete data dictionary with all needed information
            invoice_data = {
                "vendor_name": vendor_name,
                "vendor_number": vendor_number,
                "invoice_number": invoice_number,
                "po_number": po_number,
                "invoice_date": self.format_date(invoice_date),
                "terms": terms,
                "due_date": self.format_date(due_date),
                "total_amount": final_amount,
                "acct_no": "0697-099",
                "cp_acct_no": "0697-099"
            }
            
            rows_to_export.append(invoice_data)
            print(f"[INFO] Prepared row {row} for export: {vendor_name} ({vendor_number})")
    
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