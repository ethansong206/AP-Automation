import re
import string
from .common_extraction import normalize_words, find_label_positions, find_value_to_right
from .utils import clean_currency

def extract_total_amount(words, vendor_name):
    """Extract the total amount from OCR words, returns a float or empty string."""

    # --- Special-case vendor/label mapping ---
    special_vendor_labels = {
        "Topo Designs LLC": "amount due",
        "NOCS Provisions": "amount due",
        "Merrell": "amount due",
        "Accent & Cannon": "Balance Due",
        "NuCanoe": "balance due",
        "KATIN": "balance due",
        "BIG Adventures, LLC": "balance due",
        "Fulling Mill Fly Fishing LLC": "amount to pay",
        "Treadlabs": "outstanding",
        "Industrial Revolution, Inc": "remaining amount",
        "Yakima": "Balance:",
    }

    label = special_vendor_labels.get(vendor_name)

    # --- Currency pattern ---
    amount_pattern = r'^-?\$?-?(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}$T?'

    def is_currency(text):
        value = preprocess_currency_text(text.strip())
        return re.match(amount_pattern, value) is not None

    normalized_words = normalize_words(words, first_page_only=True)

    # --- Special-case logic ---
    if label:
        print(f"[DEBUG] Special-case vendor detected: {vendor_name} (label: {label})")
        # Use find_label_positions to find the label
        label_positions = find_label_positions(normalized_words, label_type=None, custom_label=label)
        print(f"[DEBUG] Found {len(label_positions)} label positions for '{label}'")
        # Use find_value_to_right to find the first valid currency value to the right
        value = find_value_to_right(
            normalized_words,
            label_positions,
            is_currency,
            strict=True
        )
        if value:
            cleaned = clean_currency(preprocess_currency_text(value))
            try:
                amount = float(cleaned)
                print(f"[DEBUG] Selected special-case amount: {value} → {amount:.2f}")
                return f"{amount:.2f}"
            except Exception:
                print(f"[DEBUG] Failed to convert '{value}' to float")
        print("[DEBUG] Special-case label found, but no valid value to right. Falling back to general logic.")

    # --- General logic (existing) ---
    candidates = []
    for word in words:
        value = word["text"].strip()
        value = preprocess_currency_text(value)
        if re.match(amount_pattern, value):
            cleaned = clean_currency(value)
            try:
                amount = float(cleaned)
                candidates.append({
                    'raw': value,
                    'amount': amount
                })
                print(f"[DEBUG] Found candidate amount: {value} → {amount:.2f}")
            except ValueError:
                continue

    if not candidates:
        print("[DEBUG] No valid currency amounts found")
        return ""

    # Find the amount with largest absolute value
    largest_abs = max(candidates, key=lambda x: abs(x['amount']))

    # Check if there's a negative amount with the same absolute value
    negative_match = next(
        (x for x in candidates if abs(x['amount']) == abs(largest_abs['amount']) and x['amount'] < 0),
        None
    )

    # Prefer negative amount if it exists with same absolute value
    result = negative_match if negative_match else largest_abs
    print(f"[DEBUG] Selected amount: {result['raw']} → {result['amount']:.2f}")

    return f"{result['amount']:.2f}"

def preprocess_currency_text(text):
    """Handle specific currency-related CIDs and symbols"""
    # Only handle known currency CIDs
    currency_cid_map = {
        "(cid:36)": "$",  # Dollar sign
        # Add others as needed
    }
    for cid, symbol in currency_cid_map.items():
        text = text.replace(cid, symbol)
    return text