import os
import csv
import re
from datetime import datetime

# Define headers for the accounting system import format
VCHR_HEADER = [
    "1-AI_VCHR", "VCHR_VEND_NO", "VCHR_NO", "BAT_ID", "VCHR_DIST_DAT", 
    "VCHR_INVC_DAT", "VCHR_INVC_NO", "VCHR_REF", "VEND_NAM", "NON_DISC_AMT",
    "DUE_DAT", "DISC_DAT", "DISC_AMT", "VARIANCE_AMT", "PO_NO",
    "VCHR_MISC_AMT_1", "VCHR_MISC_AMT_2", "VCHR_MISC_AMT_3", "VCHR_MISC_AMT_4", "VCHR_MISC_AMT_5",
    "VCHR_TOT_MISC", "VCHR_SUB_TOT", "VCHR_SUB_TOT_LANDED", "VCHR_TOT", 
    "LIN_MISC_CHRG_1", "LIN_MISC_CHRG_2", "LIN_MISC_CHRG_3", "LIN_MISC_CHRG_4", "LIN_MISC_CHRG_5",
    "TOT_LIN_MISC_CHRG", "NO_OF_RECVRS", "RECVR_MISC_AMT_1", "RECVR_MISC_AMT_2", "RECVR_MISC_AMT_3",
    "RECVR_MISC_AMT_4", "RECVR_MISC_AMT_5", "RECVR_TOT_MISC", "RECVR_SUB_TOT", "RECVR_TOT",
    "TERMS_COD", "DUE_DAYS", "DISC_DAYS", "DISC_PCT", "DISC_ACCT_NO", "CP_DISC_ACCT_NO", "SPEC_TERMS", "VEND_TERMS"
]

DIST_HEADER = [
    "2-AI_VCHR_DIST", "VCHR_VEND_NO", "VCHR_NO", "SEQ_NO", "ACCT_NO", "CP_ACCT_NO", "AMT"
]

# Default accounts
DEFAULT_INVENTORY_ACCT = "0697-099"
DEFAULT_DISCOUNT_ACCT = "0697-099"  # Changed from 0520-002
DEFAULT_CP_DISCOUNT_ACCT = ""       # Changed to empty string

def export_accounting_csv(filename, invoice_table):
    """Export invoices to accounting system format with multiple record types."""
    try:
        print(f"[INFO] Starting export to {filename}")
        print(f"[INFO] Table has {invoice_table.rowCount()} rows")
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile, quoting=csv.QUOTE_ALL)
            
            # Write the record type headers
            writer.writerow(VCHR_HEADER)
            writer.writerow(DIST_HEADER)
            
            # Process each invoice row
            rows_written = 0
            for row in range(invoice_table.rowCount()):
                print(f"[INFO] Processing row {row}")
                
                # Get vendor name for lookup - ensure aggressive cleaning
                raw_vendor_name = invoice_table.get_cell_text(row, 0)
                vendor_name = re.sub(r'\s+', ' ', raw_vendor_name.replace("• ", "").strip())

                if not vendor_name or vendor_name.upper() == "ADD VENDOR":
                    print(f"[INFO] Skipping row {row}: Invalid vendor '{vendor_name}'")
                    continue

                # Get vendor ID
                vendor_id = get_vendor_id(vendor_name)
                if vendor_id == "0":  # Default unknown ID
                    print(f"[WARN] Using default vendor ID for '{vendor_name}'")
                
                # Get other invoice data
                invoice_no = clean_text(invoice_table.get_cell_text(row, 1))
                po_no = clean_text(invoice_table.get_cell_text(row, 2))
                invoice_date = clean_text(invoice_table.get_cell_text(row, 3))
                terms = clean_text(invoice_table.get_cell_text(row, 4))
                due_date = clean_text(invoice_table.get_cell_text(row, 5))
                disc_amount = clean_text(invoice_table.get_cell_text(row, 6))
                total_amount = clean_text(invoice_table.get_cell_text(row, 7))
                
                # Validate required fields
                if not invoice_no or not invoice_date or not total_amount:
                    print(f"[INFO] Skipping row {row}: Missing required data")
                    continue
                
                # Calculate needed values
                batch_id = "AP-0001"  # Default batch ID
                dist_date = format_date_for_export(datetime.now())
                invoice_date_formatted = format_date_for_export(parse_date(invoice_date))
                due_date_formatted = format_date_for_export(parse_date(due_date))
                
                # Parse terms information
                terms_info = parse_terms(terms)
                terms_code = terms_info['code']
                due_days = terms_info['due_days']
                
                # Clean up amounts
                clean_total = clean_amount(total_amount)
                clean_disc = clean_amount(disc_amount) if disc_amount else "0.00"
                
                # Write invoice header record (1-AI_VCHR)
                vchr_row = ["1-AI_VCHR", vendor_id, invoice_no, batch_id, dist_date, 
                          invoice_date_formatted, invoice_no, "", vendor_name, "0.00",
                          due_date_formatted, invoice_date_formatted, clean_disc, "0.00", po_no]
                
                # Add misc amounts - CHANGED: All set to 0.00
                for i in range(5):  # VCHR_MISC_AMT_1 through 5
                    vchr_row.append("0.00")
                
                # Add totals - CHANGED: VCHR_TOT_MISC set to 0.00
                vchr_row.append("0.00")  # VCHR_TOT_MISC
                vchr_row.append(clean_total)  # VCHR_SUB_TOT
                vchr_row.append(clean_total)  # VCHR_SUB_TOT_LANDED
                vchr_row.append(clean_total)  # VCHR_TOT
                
                # Add line misc charges (all 0)
                for i in range(5):
                    vchr_row.append("0.00")
                vchr_row.append("0.00")  # TOT_LIN_MISC_CHRG
                
                # Add receiver counts and amounts
                vchr_row.append("1")  # NO_OF_RECVRS
                for i in range(5):
                    vchr_row.append("0.00")  # RECVR_MISC_AMT_1 through 5
                vchr_row.append("0.00")  # RECVR_TOT_MISC
                
                # CHANGED: RECVR_SUB_TOT and RECVR_TOT set to 0.00
                vchr_row.append("0.00")  # RECVR_SUB_TOT
                vchr_row.append("0.00")  # RECVR_TOT
                
                # Add terms information
                # CHANGED: Set terms code and due days according to specifications
                vchr_row.append(terms_code)  # TERMS_COD - Format Nxx
                vchr_row.append(str(due_days))  # DUE_DAYS - Numeric part only
                vchr_row.append(str(terms_info['disc_days']))
                vchr_row.append(format_float(terms_info['disc_pct']))
                
                # CHANGED: Account numbers as requested
                vchr_row.append(DEFAULT_DISCOUNT_ACCT)  # Now 0697-099
                vchr_row.append(DEFAULT_CP_DISCOUNT_ACCT)  # Now empty string
                vchr_row.append("")  # SPEC_TERMS
                vchr_row.append("")  # VEND_TERMS
                
                writer.writerow(vchr_row)
                
                # Write main distribution line (inventory account)
                dist_row = ["2-AI_VCHR_DIST", vendor_id, invoice_no, "0", 
                          DEFAULT_INVENTORY_ACCT, DEFAULT_INVENTORY_ACCT, 
                          clean_total]
                writer.writerow(dist_row)
                
                print(f"[INFO] Successfully wrote row {row} for {vendor_name} (ID: {vendor_id})")
                rows_written += 1
            
            print(f"[INFO] Export completed: {rows_written} rows written")
            return True, f"Successfully exported {rows_written} invoices to {filename}."
    except Exception as e:
        print(f"[ERROR] Export failed: {str(e)}")
        return False, f"Export failed: {str(e)}"

def is_row_valid_for_export(invoice_table, row):
    """Check if row is valid for export (no errors, complete data)"""
    # Get required fields
    vendor_name = invoice_table.get_cell_text(row, 0)
    invoice_no = invoice_table.get_cell_text(row, 1)
    invoice_date = invoice_table.get_cell_text(row, 3)
    total_amount = invoice_table.get_cell_text(row, 7)
    
    # Log validation details
    print(f"Validating row {row}: Vendor='{vendor_name}', Invoice='{invoice_no}', Total='{total_amount}'")
    
    # Check for empty vendor name or "ADD VENDOR"
    if not vendor_name or vendor_name.strip().upper() == "ADD VENDOR":
        print(f"[INFO] Row {row} skipped: Missing or invalid vendor name")
        return False
    
    # Check for invoice number
    if not invoice_no or invoice_no.strip() == "":
        print(f"[INFO] Row {row} skipped: Missing invoice number")
        return False
    
    # Check for invoice date
    if not invoice_date or invoice_date.strip() == "":
        print(f"[INFO] Row {row} skipped: Missing invoice date")
        return False
    
    # Check for total amount
    if not total_amount or total_amount.strip() == "":
        print(f"[INFO] Row {row} skipped: Missing total amount")
        return False
    
    # Row is valid
    print(f"[INFO] Row {row} is valid for export")
    return True

def get_vendor_id(vendor_name):
    """Get vendor number from vendor name using vendors.csv file."""
    if not vendor_name:
        print(f"[WARN] Empty vendor name")
        return "0"  # Default vendor ID
    
    # Extra aggressive cleaning - convert all whitespace sequences to single spaces
    # This directly addresses spaces being preserved in the table text
    original = vendor_name  # Save for logging
    vendor_name = re.sub(r'\s+', ' ', vendor_name.replace("• ", "").strip())
    
    print(f"[DEBUG] Vendor lookup: '{original}' → '{vendor_name}'")
    
    if vendor_name.upper() == "ADD VENDOR":
        return "0"
    
    # Look up vendor ID in vendors.csv
    try:
        with open('data/vendors.csv', 'r', encoding='utf-8') as f:
            reader = csv.reader(f)
            for row in reader:
                if len(row) >= 2:
                    # In vendors.csv, format is: VendorNo,VendorName
                    vendor_id = row[0].strip()
                    csv_vendor_name = row[1].strip()
                    
                    # Apply same space normalization to CSV data
                    csv_vendor_name = re.sub(r'\s+', ' ', csv_vendor_name)
                    
                    # Case-insensitive comparison
                    if csv_vendor_name.lower() == vendor_name.lower():
                        print(f"[INFO] ✓ Found vendor ID '{vendor_id}' for '{vendor_name}'")
                        return vendor_id
    except Exception as e:
        print(f"[ERROR] Could not read vendors.csv: {e}")
    
    print(f"[WARN] No vendor ID found for '{vendor_name}'. Using default '0'.")
    return "0"  # Default vendor ID when not found

def format_date_for_export(date_obj):
    """Format date as MM/DD/YYYY for export"""
    return date_obj.strftime("%m/%d/%Y")

def parse_date(date_string):
    """Parse date from MM/dd/yy format"""
    try:
        # Remove bullet points if present
        clean_date = date_string.replace("• ", "").strip()
        
        if '/' in clean_date:
            parts = clean_date.split('/')
            if len(parts) == 3:
                month = int(parts[0])
                day = int(parts[1])
                year = int(parts[2])
                
                # Handle 2-digit years
                if year < 100:
                    year += 2000
                    
                return datetime(year, month, day)
    except:
        pass
        
    return datetime.now()  # Fallback

def clean_amount(amount_str):
    """Clean amount string for export"""
    # Remove any non-numeric characters except decimal point and negative sign
    value = re.sub(r'[^\d.-]', '', amount_str)
    
    # Handle empty string
    if not value:
        return "0.00"
        
    # Ensure proper format
    try:
        return format_float(float(value))
    except:
        return "0.00"

def format_float(value):
    """Format float to 2 decimal places"""
    return f"{float(value):.2f}"

def clean_text(text):
    """
    Clean text for export and comparison:
    1. Remove bullet points
    2. Normalize all whitespace (including internal spaces)
    3. Trim leading/trailing whitespace
    """
    if not text:
        return ""
    
    # Remove bullet points
    cleaned = text.replace("• ", " ")
    
    # Normalize all whitespace to single spaces (handles multiple spaces, tabs, etc.)
    cleaned = ' '.join(cleaned.split())
    
    # Final trim
    return cleaned.strip()

def parse_terms(terms_string):
    """Parse terms string to extract terms code, due days, discount days and percentage"""
    result = {
        'code': 'N30',  # Default to N30
        'due_days': 30,  # Default to 30 days
        'disc_days': 0,
        'disc_pct': 0.000
    }
    
    if not terms_string:
        return result
        
    # Look for common patterns
    terms_string = terms_string.upper().strip()
    
    # Net X days (e.g., NET 30, N30)
    net_match = re.search(r'N(?:ET)?\s*(\d+)', terms_string)
    if net_match:
        days = int(net_match.group(1))
        result['code'] = f"N{days}"  # Ensure format is Nxx not NET xx
        result['due_days'] = days
        
        # Check for discount terms (e.g., 2/10 NET 30)
        disc_match = re.search(r'(\d+(?:\.\d+)?)\s*[/%]\s*(\d+)', terms_string)
        if disc_match:
            result['disc_pct'] = float(disc_match.group(1))
            result['disc_days'] = int(disc_match.group(2))
    
    return result

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller"""
    import sys
    import os
    try:
        # PyInstaller
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def write_to_csv(filename, data_source):
    """
    Write invoice data to CSV file in accounting system format.
    Handles both QTableWidget objects and pre-formatted data lists.
    """
    try:
        if hasattr(data_source, 'rowCount'):
            print(f"[INFO] Processing QTableWidget with {data_source.rowCount()} rows")
            return export_accounting_csv(filename, data_source)
        else:
            print(f"[INFO] Processing pre-formatted list with {len(data_source)} rows")
            
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile, quoting=csv.QUOTE_ALL)
                
                # Write the record type headers
                writer.writerow(VCHR_HEADER)
                writer.writerow(DIST_HEADER)
                
                # Process each invoice row from the list
                for row_data in data_source:
                    if len(row_data) < 9:
                        print(f"[WARN] Skipping invalid row: {row_data}")
                        continue
                    
                    # Extract data from the pre-formatted row
                    vendor_id = clean_text(row_data[0]) or "0"
                    invoice_date = clean_text(row_data[1])
                    invoice_no = clean_text(row_data[2])
                    vendor_name = clean_text(row_data[3])
                    due_date = clean_text(row_data[4])
                    po_no = clean_text(row_data[5])
                    acct_no = row_data[6]
                    cp_acct_no = row_data[7]
                    amount = clean_amount(row_data[8])
                    
                    # Format for accounting system
                    batch_id = "AP-0001"
                    dist_date = format_date_for_export(datetime.now())
                    
                    # Build the row with exactly 47 columns to match VCHR_HEADER
                    vchr_row = ["1-AI_VCHR", vendor_id, invoice_no, batch_id, dist_date, 
                              invoice_date, invoice_no, "", vendor_name, "0.00",
                              due_date, invoice_date, "0.00", "0.00", po_no]
                    
                    # Add misc amounts (cols 16-20)
                    for i in range(5):
                        vchr_row.append("0.00")
                    
                    # Add totals (cols 21-24)
                    vchr_row.append("0.00")  # VCHR_TOT_MISC
                    vchr_row.append(amount)  # VCHR_SUB_TOT
                    vchr_row.append(amount)  # VCHR_SUB_TOT_LANDED
                    vchr_row.append(amount)  # VCHR_TOT
                    
                    # Add line misc charges (cols 25-29)
                    for i in range(5):
                        vchr_row.append("0.00")
                    
                    # TOT_LIN_MISC_CHRG (col 30)
                    vchr_row.append("0.00")
                    
                    # NO_OF_RECVRS (col 31)
                    vchr_row.append("1")
                    
                    # RECVR_MISC_AMT_1 through 5 (cols 32-36)
                    for i in range(5):
                        vchr_row.append("0.00")
                    
                    # RECVR_TOT_MISC (col 37)
                    vchr_row.append("0.00")
                    
                    # RECVR_SUB_TOT and RECVR_TOT (cols 38-39)
                    vchr_row.append("0.00")
                    vchr_row.append("0.00")
                    
                    # TERMS_COD, DUE_DAYS, DISC_DAYS, DISC_PCT (cols 40-43)
                    vchr_row.append("N30")
                    vchr_row.append("30")
                    vchr_row.append("0")
                    vchr_row.append("0.000")
                    
                    # DISC_ACCT_NO, CP_DISC_ACCT_NO, SPEC_TERMS, VEND_TERMS (cols 44-47)
                    vchr_row.append(DEFAULT_DISCOUNT_ACCT)
                    vchr_row.append(DEFAULT_CP_DISCOUNT_ACCT)
                    vchr_row.append("")
                    vchr_row.append("")
                    
                    # Verify we have exactly 47 columns
                    if len(vchr_row) != 47:
                        print(f"[ERROR] Generated row has {len(vchr_row)} columns instead of 47!")
                        
                    writer.writerow(vchr_row)
                    
                    # Write distribution record
                    dist_row = ["2-AI_VCHR_DIST", vendor_id, invoice_no, "0", 
                              acct_no, cp_acct_no, amount]
                    writer.writerow(dist_row)
                
                return True, f"Successfully exported {len(data_source)} invoices to {filename}"
    except Exception as e:
        print(f"[ERROR] Export failed: {str(e)}")
        return False, f"Export failed: {str(e)}"

def format_and_write_csv(filename, invoice_data_list):
    """
    Format invoice data and write to CSV in accounting system format.
    
    Args:
        filename: Path to output CSV file
        invoice_data_list: List of invoice data dictionaries
    """
    try:
        print(f"[INFO] Writing {len(invoice_data_list)} invoices to {filename}")
        
        with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile, quoting=csv.QUOTE_ALL)
            
            # Write the record type headers
            writer.writerow(VCHR_HEADER)
            writer.writerow(DIST_HEADER)
            
            # Process each invoice
            for invoice in invoice_data_list:
                # Extract values from the dictionary
                vendor_name = invoice["vendor_name"]
                vendor_id = invoice["vendor_number"]
                invoice_no = invoice["invoice_number"]
                po_no = invoice["po_number"]
                invoice_date = invoice["invoice_date"]
                terms = invoice["terms"]
                due_date = invoice["due_date"]
                amount = clean_amount(invoice["total_amount"])
                acct_no = invoice["acct_no"]
                cp_acct_no = invoice["cp_acct_no"]
                
                # Calculate additional values
                batch_id = "AP-0001"
                dist_date = format_date_for_export(datetime.now())
                invoice_date_formatted = format_date_for_export(parse_date(invoice_date))
                due_date_formatted = format_date_for_export(parse_date(due_date))
                
                # Parse terms
                terms_info = parse_terms(terms)
                
                # Build the invoice header record (1-AI_VCHR) - exactly 47 columns
                vchr_row = ["1-AI_VCHR", vendor_id, invoice_no, batch_id, dist_date, 
                          invoice_date_formatted, invoice_no, "", vendor_name, "0.00",
                          due_date_formatted, invoice_date_formatted, "0.00", "0.00", po_no]
                
                # Add misc amounts (cols 16-20)
                for i in range(5):
                    vchr_row.append("0.00")
                
                # Add totals (cols 21-24)
                vchr_row.append("0.00")  # VCHR_TOT_MISC
                vchr_row.append(amount)  # VCHR_SUB_TOT
                vchr_row.append(amount)  # VCHR_SUB_TOT_LANDED
                vchr_row.append(amount)  # VCHR_TOT
                
                # Add line misc charges (cols 25-29)
                for i in range(5):
                    vchr_row.append("0.00")
                
                # TOT_LIN_MISC_CHRG (col 30)
                vchr_row.append("0.00")
                
                # NO_OF_RECVRS (col 31)
                vchr_row.append("1")
                
                # RECVR_MISC_AMT_1 through 5 (cols 32-36)
                for i in range(5):
                    vchr_row.append("0.00")
                
                # RECVR_TOT_MISC (col 37)
                vchr_row.append("0.00")
                
                # RECVR_SUB_TOT and RECVR_TOT (cols 38-39)
                vchr_row.append("0.00")
                vchr_row.append("0.00")
                
                # TERMS_COD, DUE_DAYS, DISC_DAYS, DISC_PCT (cols 40-43)
                vchr_row.append(terms_info['code'])
                vchr_row.append(str(terms_info['due_days']))
                vchr_row.append(str(terms_info['disc_days']))
                vchr_row.append(format_float(terms_info['disc_pct']))
                
                # DISC_ACCT_NO, CP_DISC_ACCT_NO, SPEC_TERMS, VEND_TERMS (cols 44-47)
                vchr_row.append(DEFAULT_DISCOUNT_ACCT)
                vchr_row.append(DEFAULT_CP_DISCOUNT_ACCT)
                vchr_row.append("")
                vchr_row.append("")
                
                # Verify we have exactly 47 columns
                if len(vchr_row) != 47:
                    print(f"[ERROR] Generated row has {len(vchr_row)} columns instead of 47!")
                    
                writer.writerow(vchr_row)
                
                # Write distribution record
                dist_row = ["2-AI_VCHR_DIST", vendor_id, invoice_no, "0", 
                          acct_no, cp_acct_no, amount]
                writer.writerow(dist_row)
                
                print(f"[INFO] Wrote invoice: {vendor_name} ({vendor_id}) - {invoice_no}")
            
            return True, f"Successfully exported {len(invoice_data_list)} invoices to {filename}"
    except Exception as e:
        print(f"[ERROR] Export failed: {str(e)}")
        return False, f"Export failed: {str(e)}"
