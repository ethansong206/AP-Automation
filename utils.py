import os
import csv
import json
import shutil
import re
from datetime import datetime
from PyQt5.QtCore import QStandardPaths


def _should_write_headers(filename: str) -> bool:
    """Return True if we should write headers (new or empty file)."""
    try:
        return (not os.path.exists(filename)) or os.path.getsize(filename) == 0
    except Exception:
        # If in doubt, be safe and write headers
        return True

def _scan_existing_voucher_rows(filename: str) -> set[tuple]:
    """Return a set of existing voucher rows from an export file.

    Each voucher row (tagged with ``1-AI_VCHR``) is stored as a tuple of strings
    for exact comparison. Distribution rows and headers are ignored. This allows
    duplicate detection to compare only the voucher portion of each invoice.
    """
    vouchers: set[tuple] = set()
    if not os.path.exists(filename) or os.path.getsize(filename) == 0:
        return vouchers

    try:
        with open(filename, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            for row in reader:
                if not row:
                    continue
                if row == VCHR_HEADER or row == DIST_HEADER:
                    continue
                tag = row[0].strip()
                if tag == "1-AI_VCHR":
                    vouchers.add(tuple(row))
    except Exception:
        return set()

    return vouchers

# Define headers for the simplified accounting system import format
# These headers mirror the example provided by the accounting team. Each
# header line contains 48 columns.
VCHR_HEADER = [
    "1-AI_VCHR", "VendorNo", "InvoiceNo", "InvoiceDate", 
    "InvoiceDueDate", "Comment(PO)", "VendorName"
]

DIST_HEADER = [
    "2-AI_VCHR_DIST",
    "AccountNo",
    "DistributionAmt"
]

def is_row_valid_for_export(invoice_table, row):
    """Check if row is valid for export (no errors, complete data)"""
    # Get required fields
    vendor_name = invoice_table.get_cell_text(row, 1)
    invoice_no = invoice_table.get_cell_text(row, 2)
    invoice_date = invoice_table.get_cell_text(row, 4)
    total_amount = invoice_table.get_cell_text(row, 8)
    
    # Log validation details
    print(f"Validating row {row}: Vendor='{vendor_name}', Invoice='{invoice_no}', Total='{total_amount}'")
    
    # Check for empty vendor name
    if not vendor_name:
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
    vendor_name = re.sub(r'\s+', ' ', vendor_name.strip())
    
    print(f"[DEBUG] Vendor lookup: '{original}' → '{vendor_name}'")
    
    if not vendor_name:
        return "0"
    
    # Look up vendor ID in vendors.csv
    try:
        csv_path = get_vendor_csv_path()
        with open(csv_path, 'r', encoding='utf-8') as f:
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
        clean_date = date_string.strip()
        
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
    1. Normalize all whitespace (including internal spaces)
    2. Trim leading/trailing whitespace
    """
    if not text:
        return ""
    
    cleaned = ' '.join(text.split())
    
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
        
    # Normalize input for regex matching
    terms_string = terms_string.upper().strip()
    
    # Primary patterns
    net_match = re.search(r'N(?:ET)?\s*(\d+)', terms_string)  # NET 30 or N30
    disc_match = re.search(r'(\d+(?:\.\d+)?)\s*[/%]\s*(\d+)', terms_string)  # 2/10 or 2%10
    
    if net_match:
        # Explicit NET term provided
        days = int(net_match.group(1))
        result['code'] = f"N{days}"
        result['due_days'] = days

        if disc_match:
            result['disc_pct'] = float(disc_match.group(1))
            result['disc_days'] = int(disc_match.group(2))

    elif disc_match:
        # Handle formats without explicit NET (e.g., "8% 75")
        days = int(disc_match.group(2))
        result['code'] = f"N{days}"
        result['due_days'] = days
        result['disc_pct'] = float(disc_match.group(1))
        result['disc_days'] = 0

    else:
        # Fallback: any standalone number becomes NET days
        num_match = re.search(r'(\d+)', terms_string)
        if num_match:
            days = int(num_match.group(1))
            result['code'] = f"N{days}"
            result['due_days'] = days
    
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

def _appdata_dir() -> str:
    """Return writable application data directory, creating it if needed."""
    # Use consistent "AP Automation" folder instead of Qt's versioned AppDataLocation
    roaming_root = os.getenv("APPDATA") or os.path.expanduser("~")
    base = os.path.join(roaming_root, "AP Automation")
    
    # Migrate from old versioned Qt folders if they exist
    if not os.path.exists(base):
        _migrate_from_qt_appdata(roaming_root, base)
    
    if not os.path.exists(base):
        os.makedirs(base, exist_ok=True)
    return base


def _migrate_from_qt_appdata(roaming_root: str, target_dir: str) -> None:
    """Migrate data from old Qt AppDataLocation folders to standardized location."""
    # Look for existing "AP Automation" folders with version suffixes
    try:
        for item in os.listdir(roaming_root):
            item_path = os.path.join(roaming_root, item)
            if (os.path.isdir(item_path) and 
                item.startswith("AP Automation") and 
                item != "AP Automation"):
                
                # Found an old versioned folder - migrate its contents
                print(f"[INFO] Migrating data from {item} to AP Automation")
                
                # Create target directory
                os.makedirs(target_dir, exist_ok=True)
                
                # Move vendors.csv if it exists
                old_vendors = os.path.join(item_path, "vendors.csv")
                new_vendors = os.path.join(target_dir, "vendors.csv")
                if os.path.exists(old_vendors) and not os.path.exists(new_vendors):
                    shutil.move(old_vendors, new_vendors)
                    print(f"[INFO] Migrated vendors.csv from {item}")
                
                # Move manual_vendor_map.json if it exists
                old_map = os.path.join(item_path, "manual_vendor_map.json")
                new_map = os.path.join(target_dir, "manual_vendor_map.json")
                if os.path.exists(old_map) and not os.path.exists(new_map):
                    shutil.move(old_map, new_map)
                    print(f"[INFO] Migrated manual_vendor_map.json from {item}")
                
                # Only migrate from the first found folder to avoid conflicts
                break
                
    except Exception as e:
        print(f"[WARN] Could not migrate from old AppData folders: {e}")


def _add_rows_with_duplicate_prevention(existing_rows: list[dict], new_rows: list[dict]) -> None:
    """Add new rows to existing_rows, preventing exact duplicates."""
    # Create a set of existing row signatures for fast duplicate detection
    existing_signatures = set()
    for row in existing_rows:
        signature = (
            (row.get("Vendor No. (Sage)", "") or "").strip(),
            (row.get("Vendor Name", "") or "").strip().lower(),
            (row.get("Identifier", "") or "").strip()
        )
        existing_signatures.add(signature)
    
    # Add new rows that don't already exist
    for new_row in new_rows:
        new_signature = (
            (new_row.get("Vendor No. (Sage)", "") or "").strip(),
            (new_row.get("Vendor Name", "") or "").strip().lower(),
            (new_row.get("Identifier", "") or "").strip()
        )
        
        if new_signature not in existing_signatures:
            existing_rows.append(new_row)
            existing_signatures.add(new_signature)
            print(f"[INFO] Added vendor: {new_row.get('Vendor Name', '')} (#{new_row.get('Vendor No. (Sage)', '')})")
        else:
            print(f"[INFO] Skipped duplicate vendor: {new_row.get('Vendor Name', '')} (#{new_row.get('Vendor No. (Sage)', '')})")


def _merge_vendors_csv(src: str, dest: str) -> None:
    """Merge default vendors.csv into user copy with interactive conflict resolution."""
    user_rows: list[dict] = []
    if os.path.exists(dest):
        with open(dest, newline="", encoding="utf-8-sig") as f:
            user_rows = list(csv.DictReader(f))
    
    src_rows: list[dict] = []
    if os.path.exists(src):
        with open(src, newline="", encoding="utf-8-sig") as f:
            src_rows = list(csv.DictReader(f))
    
    # Upgrade 2-column format to 3-column format if needed
    if user_rows and "Identifier" not in user_rows[0]:
        for row in user_rows:
            if "Identifier" not in row:
                row["Identifier"] = ""
    
    # Ensure all src_rows have 3 columns
    for row in src_rows:
        if "Identifier" not in row:
            row["Identifier"] = ""
    
    # Analyze conflicts and changes
    conflicts = []
    additions = []
    
    # Create lookup dictionaries for efficient comparison
    user_by_number = {(r.get("Vendor No. (Sage)", "") or "").strip(): r for r in user_rows}
    user_by_name = {(r.get("Vendor Name", "") or "").strip().lower(): r for r in user_rows}
    
    for src_row in src_rows:
        src_number = (src_row.get("Vendor No. (Sage)", "") or "").strip()
        src_name = (src_row.get("Vendor Name", "") or "").strip()
        src_name_lower = src_name.lower()
        src_identifier = (src_row.get("Identifier", "") or "").strip()
        
        # Skip empty rows
        if not src_number and not src_name:
            continue
            
        user_row_by_number = user_by_number.get(src_number)
        user_row_by_name = user_by_name.get(src_name_lower)
        
        # Case 1: Same vendor number, different vendor name
        # Skip conflicts for vendor number 000000 (placeholder/unknown vendors)
        if (user_row_by_number and src_number != "000000" and
            (user_row_by_number.get("Vendor Name", "") or "").strip().lower() != src_name_lower):
            conflicts.append({
                'type': 'number_conflict',
                'user_row': user_row_by_number,
                'bundle_row': src_row,
                'reason': f"Same vendor number ({src_number}) but different names"
            })
            
        # Case 2: Same vendor name, different vendor number  
        elif (user_row_by_name and 
              (user_row_by_name.get("Vendor No. (Sage)", "") or "").strip() != src_number):
            conflicts.append({
                'type': 'name_conflict', 
                'user_row': user_row_by_name,
                'bundle_row': src_row,
                'reason': f"Same vendor name ({src_name}) but different numbers"
            })
            
        # Case 3: Same number and name, different identifier - keep both (handled later)
        elif (user_row_by_number and user_row_by_name and 
              user_row_by_number == user_row_by_name):
            user_identifier = (user_row_by_number.get("Identifier", "") or "").strip()
            if user_identifier != src_identifier:
                # This will be handled by keeping both entries
                pass
                
        # Case 4: Complete duplicate - skip
        elif (user_row_by_number and user_row_by_name and 
              user_row_by_number == user_row_by_name):
            user_identifier = (user_row_by_number.get("Identifier", "") or "").strip()
            if user_identifier == src_identifier:
                # Complete duplicate - skip
                continue
                
        # No conflict - can be added
        elif not user_row_by_number and not user_row_by_name:
            additions.append(src_row)
        # Special case: vendor number 000000 should always be added without conflict
        elif src_number == "000000":
            additions.append(src_row)
    
    # Handle conflicts if any exist
    final_user_rows = user_rows.copy()
    conflicts_resolved = False
    
    if conflicts:
        print(f"[INFO] Found {len(conflicts)} vendor conflicts to resolve")
        # Import here to avoid circular imports
        try:
            from views.dialogs.vendor_merge_dialog import VendorMergeDialog
            from PyQt5.QtWidgets import QApplication
            
            app = QApplication.instance()
            if app is None:
                # If no QApplication exists, we can't show dialogs
                print("[WARN] Cannot show merge dialog - no Qt application running")
                return
                
            print("[INFO] Showing merge dialog to user")
            dialog = VendorMergeDialog(conflicts)
            dialog_result = dialog.exec_()
            
            if dialog_result == dialog.Accepted:
                user_choices = dialog.get_user_choices()
                print(f"[INFO] User made choices for {len(user_choices)} conflicts")
                conflicts_resolved = True
                
                # Apply user choices
                bundle_rows_to_add = []  # Track bundle rows to add (for "both" option)
                
                for conflict_index, choice in user_choices.items():
                    conflict = conflicts[conflict_index]
                    print(f"[INFO] Conflict {conflict_index}: User chose '{choice}'")
                    
                    if choice == 'bundle':
                        # Replace user row with bundle row
                        old_row = conflict['user_row']
                        new_row = conflict['bundle_row']
                        
                        # Find and replace the old row by comparing all fields
                        replaced = False
                        for i, row in enumerate(final_user_rows):
                            # Compare all fields to find the exact match
                            if (row.get("Vendor No. (Sage)", "") == old_row.get("Vendor No. (Sage)", "") and
                                row.get("Vendor Name", "") == old_row.get("Vendor Name", "") and
                                row.get("Identifier", "") == old_row.get("Identifier", "")):
                                final_user_rows[i] = new_row
                                print(f"[INFO] Replaced vendor: {old_row.get('Vendor Name', '')} with bundle version")
                                replaced = True
                                break
                        if not replaced:
                            print(f"[WARN] Could not find row to replace for {old_row.get('Vendor Name', '')}")
                                
                    elif choice == 'both':
                        # Keep both - user row stays, add bundle row if not duplicate
                        bundle_row = conflict['bundle_row']
                        bundle_rows_to_add.append(bundle_row)
                        print(f"[INFO] Keeping both versions of vendor: {bundle_row.get('Vendor Name', '')}")
                        
                    # choice == 'user' means keep user's version (no action needed)
                
                # Add bundle rows from "both" choices, with duplicate prevention
                if bundle_rows_to_add:
                    print(f"[INFO] Adding {len(bundle_rows_to_add)} additional vendors from 'keep both' choices")
                    _add_rows_with_duplicate_prevention(final_user_rows, bundle_rows_to_add)
            else:
                # User cancelled - don't merge
                print("[INFO] User cancelled merge dialog")
                return
        except ImportError as e:
            print(f"[WARN] Could not import merge dialog: {e}")
            return
    
    # Add new vendors (no conflicts) with duplicate prevention
    _add_rows_with_duplicate_prevention(final_user_rows, additions)
    
    # Handle Case 3: Same name/number, different identifier - add as separate entry
    case3_additions = []
    for src_row in src_rows:
        src_number = (src_row.get("Vendor No. (Sage)", "") or "").strip()
        src_name = (src_row.get("Vendor Name", "") or "").strip()
        src_name_lower = src_name.lower()
        src_identifier = (src_row.get("Identifier", "") or "").strip()
        
        user_row_by_number = user_by_number.get(src_number)
        user_row_by_name = user_by_name.get(src_name_lower)
        
        if (user_row_by_number and user_row_by_name and 
            user_row_by_number == user_row_by_name):
            user_identifier = (user_row_by_number.get("Identifier", "") or "").strip()
            if user_identifier != src_identifier and src_identifier:
                # Add as separate entry
                case3_additions.append(src_row)
    
    # Add Case 3 entries with duplicate prevention
    _add_rows_with_duplicate_prevention(final_user_rows, case3_additions)
    
    # Always write the file after processing conflicts/merges
    # Even if no "additions", there may have been conflict resolutions
    should_write = (not os.path.exists(dest) or 
                   conflicts_resolved or  # Force write if user resolved conflicts
                   conflicts or           # Force write if there were any conflicts  
                   additions or 
                   len(final_user_rows) != len(user_rows))
    
    if should_write:
        print(f"[INFO] Writing updated vendors.csv with {len(final_user_rows)} entries to {dest}")
        try:
            with open(dest, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=["Vendor No. (Sage)", "Vendor Name", "Identifier"])
                writer.writeheader()
                written_count = 0
                for r in final_user_rows:
                    output_row = {
                        "Vendor No. (Sage)": r.get("Vendor No. (Sage)", ""),
                        "Vendor Name": r.get("Vendor Name", ""),
                        "Identifier": r.get("Identifier", "")
                    }
                    writer.writerow(output_row)
                    written_count += 1
            print(f"[INFO] Successfully wrote {written_count} vendors to {dest}")
        except Exception as e:
            print(f"[ERROR] Failed to write vendors file: {e}")
            raise
    else:
        print("[INFO] No vendor data changes needed")


def _merge_manual_map(src: str, dest: str) -> None:
    """Merge default manual_vendor_map.json with user's copy."""
    user_data = {}
    if os.path.exists(dest):
        with open(dest, "r", encoding="utf-8") as f:
            user_data = json.load(f)
    src_data = {}
    if os.path.exists(src):
        with open(src, "r", encoding="utf-8") as f:
            src_data = json.load(f)
    merged = {**src_data, **user_data}
    if not os.path.exists(dest) or merged != user_data:
        with open(dest, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2)


def _get_data_file(name: str, merge_fn) -> str:
    """Ensure a user-writable copy of a data file exists and merge defaults."""
    user_dir = _appdata_dir()
    user_path = os.path.join(user_dir, name)
    bundled_path = resource_path(os.path.join("data", name))
    if not os.path.exists(user_path):
        if os.path.exists(bundled_path):
            shutil.copyfile(bundled_path, user_path)
    else:
        if os.path.exists(bundled_path):
            merge_fn(bundled_path, user_path)
    return user_path

def get_vendor_csv_path() -> str:
    """Return path to vendors.csv under the standardized AP Automation directory."""
    # Use standardized "AP Automation" folder in AppData/Roaming
    user_dir = _appdata_dir()
    user_path = os.path.join(user_dir, "vendors.csv")
    print(f"[DEBUG] Vendor CSV path: {user_path}")

    bundled_path = resource_path(os.path.join("data", "vendors.csv"))
    if not os.path.exists(user_path):
        print(f"[INFO] User vendors.csv doesn't exist, copying from bundle")
        if os.path.exists(bundled_path):
            shutil.copyfile(bundled_path, user_path)
            print(f"[INFO] Copied {bundled_path} to {user_path}")
    else:
        print(f"[INFO] User vendors.csv exists, checking for merge needed")
        if os.path.exists(bundled_path):
            _merge_vendors_csv(bundled_path, user_path)
    return user_path

def get_manual_map_path() -> str:
    """Path to user-managed manual_vendor_map.json with defaults merged."""
    return _get_data_file("manual_vendor_map.json", _merge_manual_map)

def format_and_write_csv(filename, invoice_data_list):
    """Write invoices to CSV using simplified export layout for SAGE"""
    try:
        print(f"[INFO] Writing {len(invoice_data_list)} invoices to {filename}")
        
        write_headers = _should_write_headers(filename)
        existing_vouchers = _scan_existing_voucher_rows(filename) if not write_headers else set()
        mode = 'a' if not write_headers else 'w'

        with open(filename, mode, newline='', encoding='utf-8') as csvfile:
            writer = csv.writer(csvfile)

            if write_headers:
                writer.writerow(VCHR_HEADER)
                writer.writerow(DIST_HEADER)

            rows_written = 0
            rows_skipped_dup = 0

            for invoice in invoice_data_list:
                vendor_id = invoice["vendor_number"]
                invoice_no = invoice["invoice_number"]
                invoice_date = invoice["invoice_date"]
                due_date = invoice["due_date"]

                comment_po = invoice["po_number"]
                if comment_po:
                    comment_po = f"PO# {comment_po}"
                vendor_name = invoice["vendor_name"]
                total_amount = clean_amount(invoice["total_amount"])
                shipping_cost = clean_amount(invoice.get("shipping_cost", "0"))

                # Voucher row
                vchr_row = [
                    "1-AI_VCHR", vendor_id, invoice_no, invoice_date, due_date, comment_po, vendor_name
                ]
                vchr_tuple = tuple(vchr_row)
                if vchr_tuple in existing_vouchers:
                    rows_skipped_dup += 1
                    continue
                writer.writerow(vchr_row)

                # Distribution row for total amount
                dist_row_total = [
                    "2-AI_VCHR_DIST", "140-000", total_amount
                ]
                writer.writerow(dist_row_total)

                # Distribution row for shipping cost (always included)
                dist_row_ship = [
                    "2-AI_VCHR_DIST", "520-000", shipping_cost
                ]
                writer.writerow(dist_row_ship)

                existing_vouchers.add(vchr_tuple)
                rows_written += 1

        action = "Created new file" if write_headers else "Appended"
        msg = f"{action} and wrote {rows_written} invoices to {filename}"
        if rows_skipped_dup:
            msg += f" (skipped {rows_skipped_dup} duplicates)"
        return True, msg

    except Exception as e:
        print(f"[ERROR] Export failed: {str(e)}")
        return False, f"Export failed: {str(e)}"
