import os
import csv

# Define required fields for accounting system import
REQUIRED_FIELDS = [
    "VCHR_VEND_NO",
    "VCHR_INVC_DAT",
    "VCHR_INVC_NO",
    "VEND_NAM",
    "DUE_DAT",
    "PO_NO",
    "ACCT_NO",      #Always 0697-099
    "CP_ACCT_NO",   #Always 0697-099
    "AMT"
]

def write_to_csv(filename, rows):
    """
    Appends rows to a CSV file, ensuring the correct headers are present.
    If file exists but headers don't match, creates a new file with correct headers
    and preserves existing data.
    """
    file_exists = os.path.isfile(filename)
    
    if file_exists:
        # Check if existing file has correct headers
        with open(filename, 'r', newline='', encoding='utf-8') as csvfile:
            reader = csv.reader(csvfile)
            try:
                existing_headers = next(reader)  # Get first row (headers)
                headers_match = existing_headers == REQUIRED_FIELDS
            except StopIteration:
                # File exists but is empty
                headers_match = False
                
        if not headers_match:
            # Headers don't match, create new file with correct headers and copy existing data
            print(f"[INFO] Existing CSV has incorrect headers. Creating new file with correct format.")
            temp_filename = filename + '.temp'
            
            # Write correct headers and copy existing data to temp file
            with open(temp_filename, 'w', newline='', encoding='utf-8') as temp_file:
                writer = csv.writer(temp_file)
                writer.writerow(REQUIRED_FIELDS)  # Write correct headers
                
                # Copy existing data if any
                try:
                    with open(filename, 'r', newline='', encoding='utf-8') as old_file:
                        reader = csv.reader(old_file)
                        next(reader, None)  # Skip header row
                        for row in reader:
                            if len(row) >= len(REQUIRED_FIELDS):
                                writer.writerow(row[:len(REQUIRED_FIELDS)])
                            else:
                                # Pad row if it's too short
                                padded_row = row + [''] * (len(REQUIRED_FIELDS) - len(row))
                                writer.writerow(padded_row)
                except Exception as e:
                    print(f"[WARN] Error copying existing data: {e}")
                    
            # Replace old file with new one
            try:
                os.remove(filename)
                os.rename(temp_filename, filename)
            except Exception as e:
                print(f"[ERROR] Failed to replace old file: {e}")
                return
    
    # Append new rows to the file
    with open(filename, 'a', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        
        if not file_exists:
            writer.writerow(REQUIRED_FIELDS)  # Write headers if new file
            print(f"[INFO] Created new file: {filename}")
            
        for row in rows:
            writer.writerow(row)
            
    print(f"[INFO] Appended {len(rows)} rows to {filename}")

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
