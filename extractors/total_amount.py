import re
from .utils import clean_currency

def extract_total_amount(words, vendor_name):
    """Extract the total amount from OCR words, returns a float or empty string."""
    # Pattern matches numbers with decimal points, including negative amounts: -$1,234.56 or $1,234.56
    amount_pattern = r'^-?\$?(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}$'
    
    candidates = []
    
    for word in words:
        value = word["text"].strip()
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