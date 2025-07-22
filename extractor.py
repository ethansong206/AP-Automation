from extractors import (
    extract_invoice_number,
    extract_invoice_date,
    extract_total_amount,
    extract_vendor,
    extract_discount_terms
)

def extract_fields(documents):
    extracted_rows = []

    for doc in documents:
        words = doc["words"]
        file_name = doc.get("file_name", "Unknown")

        row = {
            "Vendor Name": extract_vendor(words),
            "Invoice Number": extract_invoice_number(words),
            "Invoice Date": extract_invoice_date(words),
            "Discount Terms": extract_discount_terms(words),
            "Discount Due Date": "",
            "Discounted Total": "",
            "Total Amount": extract_total_amount(words)
        }

        if row["Discount Terms"] and row["Invoice Date"] and row["Total Amount"]:
            try:
                discounted_due, discounted_total = calculate_discount_fields(
                    row["Discount Terms"], row["Invoice Date"], row["Total Amount"]
                )
                row["Discount Due Date"] = discounted_due
                row["Discounted Total"] = discounted_total
            except Exception as e:
                print(f"[WARN] Could not compute discount fields: {e}")

        extracted_rows.append([
            row["Vendor Name"], row["Invoice Number"], row["Invoice Date"],
            row["Discount Terms"], row["Discount Due Date"],
            row["Discounted Total"], row["Total Amount"]
        ])

    return extracted_rows