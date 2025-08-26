from extractors import (
    extract_invoice_number,
    extract_invoice_date,
    extract_total_amount,
    extract_vendor_name,
    extract_discount_terms,
    extract_po_number
)
from extractors.utils import calculate_discount_due_date, calculate_discounted_total, check_negative_total

def extract_fields(documents):
    extracted_rows = []

    for doc in documents:
        words = doc["words"]
        file_name = doc.get("file_name", "Unknown")

        vendor_name = extract_vendor_name(words)

        row = {
            "Vendor Name": vendor_name,
            "Invoice Number": extract_invoice_number(words, vendor_name),
            "PO Number": extract_po_number(words, vendor_name),
            "Invoice Date": extract_invoice_date(words, vendor_name),
            "Discount Terms": extract_discount_terms(words, vendor_name),
            "Discount Due Date": "",
            "Shipping Cost": "",
            "Total Amount": extract_total_amount(words, vendor_name)
        }

        if row["Discount Terms"] and row["Invoice Date"]:
            try:
                discounted_due = calculate_discount_due_date(
                    row["Discount Terms"], row["Invoice Date"]
                )
                row["Discount Due Date"] = discounted_due
                if vendor_name == "Dapper Ink LLC":
                    row["Discount Due Date"] = row["Invoice Date"] # Special case for Dapper Ink
            except Exception as e:
                print(f"[WARN] Could not compute discount due date: {e}")

        # Removed for now while changing Discounted Total to Shipping Cost
        """
        if row["Discount Terms"] and row["Total Amount"]:
            try:
                discounted_total = calculate_discounted_total(
                    row["Discount Terms"], row["Total Amount"], vendor_name
                )
                row["Shipping Cost"] = discounted_total
            except Exception as e:
                print(f"[WARN] Could not compute discounted total: {e}")
        """
                
        if row["Total Amount"]:
            row["Total Amount"] = check_negative_total(row["Total Amount"], row["Discount Terms"])

        extracted_rows.append([
            row["Vendor Name"], row["Invoice Number"], row["PO Number"], row["Invoice Date"],
            row["Discount Terms"], row["Discount Due Date"],
            row["Total Amount"], row["Shipping Cost"],
            "", "", "", "",  # QC values (Subtotal, Disc%, Disc$, Shipping)
            "false"  # QC used flag
        ])

    return extracted_rows