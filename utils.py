import os
import csv

# Define required fields (same order as table headers)
REQUIRED_FIELDS = [
    "Vendor Name", "Invoice Number", "Invoice Date",
    "Discount Terms", "Discount Due Date",
    "Discounted Total", "Total Amount"
]

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
