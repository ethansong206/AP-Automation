import os
import csv

# Define required fields (same order as table headers)
REQUIRED_FIELDS = [
    "Vendor Name", "Invoice Number", "Invoice Date",
    "Discount Terms", "Discount Due Date",
    "Discounted Total", "Total Amount"
]

def validate_row_data(row):
    """
    Returns False if any required field is empty or clearly invalid.
    Used to trigger yellow highlight.
    """
    for i, value in enumerate(row):
        if not value or value.strip() == "":
            print(f"[WARN] Missing value for '{REQUIRED_FIELDS[i]}'")
            return False
        if "total" in REQUIRED_FIELDS[i].lower():
            try:
                float(value.replace("$", "").replace(",", ""))
            except ValueError:
                print(f"[WARN] Invalid number format in '{REQUIRED_FIELDS[i]}': {value}")
                return False
    return True

def write_to_csv(filename, rows):
    """
    Appends a list of rows to an existing CSV file (creates file with headers if needed).
    """
    file_exists = os.path.isfile(filename)

    with open(filename, mode="a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)

        if not file_exists:
            writer.writerow(REQUIRED_FIELDS)  # Write headers once
            print(f"[INFO] Created new file: {filename}")

        for row in rows:
            writer.writerow(row)

    print(f"[INFO] Appended {len(rows)} rows to {filename}")
