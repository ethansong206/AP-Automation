import re
import string
import logging
from .common_extraction import normalize_words, find_label_positions, find_value_to_right
from .utils import clean_currency

def extract_total_amount(words, vendor_name):
    """Extract the total amount from OCR words, returns a float or empty string."""

     # --- Currency pattern ---
    amount_pattern = r'^-?\$?-?(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}$T?'

    def is_currency(text):
        value = preprocess_currency_text(text.strip())
        return re.match(amount_pattern, value) is not None

    # --- ON Running special-case ---
    if vendor_name == "ON Running":
        logging.debug("Special-case vendor detected: %s (searching lowest 'Total')", vendor_name)

        def normalize_label(text):
            return ''.join(c for c in text.lower() if c not in string.punctuation).strip()

        total_labels = [w for w in words if normalize_label(w.get("text", "")) == "total"]

        if total_labels:
            label_word = max(total_labels, key=lambda w: (w.get("page_num", 0), w.get("top", 0)))
            label_page = label_word.get("page_num", 0)
            label_y = label_word.get("top", 0)
            label_x1 = label_word.get("x1", 0)

            y_buffer = 10
            candidates = [
                w for w in words
                if w.get("page_num", 0) == label_page
                and w.get("x0", 0) > label_x1
                and abs(w.get("top", 0) - label_y) <= y_buffer
                and is_currency(w.get("text", ""))
            ]

            if candidates:
                best = sorted(candidates, key=lambda w: abs(w.get("top", 0) - label_y))[0]
                value = best.get("text", "")
                cleaned = clean_currency(preprocess_currency_text(value))
                try:
                    amount = float(cleaned)
                    logging.debug("Selected ON Running amount: %s → %.2f", value, amount)
                    return f"{amount:.2f}"
                except Exception:
                    logging.debug("Failed to convert '%s' to float for ON Running", value)

        logging.debug("ON Running special-case failed, falling back to general logic.")

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

    normalized_words = normalize_words(words, first_page_only=True)

    # --- Special-case logic ---
    if label:
        logging.debug("Special-case vendor detected: %s (label: %s)", vendor_name, label)
        # Use find_label_positions to find the label
        label_positions = find_label_positions(normalized_words, label_type=None, custom_label=label)
        logging.debug("Found %d label positions for '%s'", len(label_positions), label)
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
                logging.debug("Selected special-case amount: %s → %.2f", value, amount)
                return f"{amount:.2f}"
            except Exception:
                logging.debug("Failed to convert '%s' to float", value)
        logging.debug("Special-case label found, but no valid value to right. Falling back to general logic.")

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
                logging.debug("Found candidate amount: %s → %.2f", value, amount)
            except ValueError:
                continue

    if not candidates:
        logging.debug("No valid currency amounts found")
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
    logging.debug("Selected amount: %s → %.2f", result['raw'], result['amount'])

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