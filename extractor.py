from extractors import (
    extract_invoice_number,
    extract_invoice_date,
    extract_total_amount,
    extract_vendor_name,
    extract_discount_terms,
    extract_po_number,
    extract_shipping_cost,
    extract_quantity
)
from extractors.utils import calculate_discount_due_date, calculate_discounted_total, check_negative_total
from logging_config import get_logger, set_performance_mode, restore_normal_mode

logger = get_logger(__name__)

def extract_fields(documents):
    # More informative logging
    if len(documents) == 1:
        filename = documents[0].get("file_name", "Unknown")
        logger.info(f"Processing document: {filename}")
    else:
        logger.info(f"Starting batch extraction for {len(documents)} documents")

    # Enable performance mode for large batches to reduce console I/O
    if len(documents) > 5:
        set_performance_mode()

    extracted_rows = []

    # Only show progress for larger batches
    show_progress = len(documents) > 10
    progress_interval = max(1, len(documents) // 10)  # Show progress every 10%

    for i, doc in enumerate(documents, 1):
        words = doc["words"]
        file_name = doc.get("file_name", "Unknown")

        # Reduced logging frequency
        if show_progress and i % progress_interval == 0:
            logger.info(f"Processing documents: {i}/{len(documents)}")

        logger.debug(f"Processing document {i}/{len(documents)}: {file_name} ({len(words)} words)")

        vendor_name = extract_vendor_name(words)
        logger.debug(f"Extracted vendor: '{vendor_name}'")

        # Extract enhanced total amount data
        total_amount_data = extract_total_amount(words, vendor_name)

        # Extract quantity with metadata
        quantity_result = extract_quantity(words, vendor_name)
        if isinstance(quantity_result, tuple):
            quantity_value, quantity_metadata = quantity_result
        else:
            # Fallback for backward compatibility (shouldn't happen with new code)
            quantity_value = quantity_result
            quantity_metadata = {}

        row = {
            "Vendor Name": vendor_name,
            "Invoice Number": extract_invoice_number(words, vendor_name),
            "PO Number": extract_po_number(words, vendor_name),
            "Invoice Date": extract_invoice_date(words, vendor_name),
            "Discount Terms": extract_discount_terms(words, vendor_name),
            "Discount Due Date": "",
            "Shipping Cost": extract_shipping_cost(words, vendor_name),
            "Total Amount": total_amount_data.get('total_amount', '') if isinstance(total_amount_data, dict) else (str(total_amount_data) if total_amount_data is not None else ''),
            "Quantity": quantity_value,
            "_total_amount_enhanced": total_amount_data,  # Store enhanced data for QC
            "_quantity_metadata": quantity_metadata  # Store quantity extraction metadata
        }

        if row["Discount Terms"] and row["Invoice Date"]:
            try:
                # Special discount terms where due date should equal invoice date
                special_terms = [
                    "STATEMENT", "CREDIT MEMO", "CREDIT NOTE", "WARRANTY",
                    "RETURN AUTHORIZATION", "DEFECTIVE", "NO TERMS",
                    "PRODUCT RETURN", "PARTS MISSING", "DUE TODAY", "RA FOR CREDIT"
                ]
                
                if row["Discount Terms"] in special_terms:
                    # For special terms, due date equals invoice date
                    row["Discount Due Date"] = row["Invoice Date"]
                else:
                    # Normal calculation for regular discount terms
                    discounted_due = calculate_discount_due_date(
                        row["Discount Terms"], row["Invoice Date"], row["Vendor Name"]
                    )
                    row["Discount Due Date"] = discounted_due
            except Exception as e:
                logger.warning(f"Could not compute discount due date: {e}")

                
        if row["Total Amount"]:
            row["Total Amount"] = check_negative_total(row["Total Amount"], row["Discount Terms"])

        extracted_rows.append([
            row["Vendor Name"], row["Invoice Number"], row["PO Number"], row["Invoice Date"],
            row["Discount Terms"], row["Discount Due Date"],
            row["Total Amount"], row["Shipping Cost"],
            "", "", "", "",  # QC values (Subtotal, Disc%, Disc$, Shipping)
            "false",  # QC used flag
            row["Quantity"]
        ])

    # Restore normal logging
    if len(documents) > 5:
        restore_normal_mode()

    if len(extracted_rows) > 10:
        logger.info(f"Field extraction complete: processed {len(extracted_rows)} documents successfully")
    else:
        logger.debug(f"Field extraction complete: processed {len(extracted_rows)} documents successfully")
    return extracted_rows