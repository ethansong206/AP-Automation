import re
import string
from .common_extraction import normalize_words, find_label_positions, find_value_to_right
from .utils import clean_currency

def extract_total_amount(words, vendor_name):
    """Extract the total amount from OCR words, returns a float or empty string."""
    
    #print(f"[TOTAL_DEBUG] Starting extraction for vendor: {vendor_name}")

    # --- Vendor-specific approach mapping for 100% success vendors ---
    VENDOR_APPROACH_MAP = {
        # Gross approach vendors (100% success)
        'Sendero Provisions Co., LLC': 'gross',
        'Yak Attack': 'gross',
        'Marine Layer': 'gross', 
        'Wapsi Fly': 'gross',
        'Columbia Sportswear': 'gross',
        'The North Face': 'gross',
        'Hareline Dubbin, Inc': 'gross',
        'Industrial Revolution, Inc': 'gross',
        'Korkers Products, LLC': 'gross',
        'ON Running': 'gross',
        'Oregon Freeze Dry': 'gross',
        'Outdoor Research': 'gross',
        'Waboba Inc': 'gross',
        'Birkenstock USA': 'gross',
        
        # Calculated approach vendors (100% success, not already in gross)
        'Howler Brothers': 'calculated',
        'Oboz Footwear LLC': 'calculated',
        'Osprey Packs, Inc': 'calculated',
        'Temple Fork Outfitters': 'calculated',
        'National Geographic Maps': 'calculated',
        'Toad & Co': 'calculated',
        'Astral Footwear': 'calculated',
        'Eagles Nest Outfitters, Inc.': 'calculated',
        'Fulling Mill Fly Fishing LLC': 'calculated',
        'Olukai LLC': 'calculated',
        
        # Bottom-most approach vendors (100% success, not in above)
        'Hobie Cat Company II, LLC': 'bottom_most',
        'TOPO ATHLETIC': 'bottom_most', 
        'Free Fly Apparel': 'bottom_most',
        'Patagonia': 'bottom_most',
        'Black Diamond Equipment Ltd': 'bottom_most',
        
        # Bottom-minus-shipping approach vendors (100% success, unique to this approach)
        'Angler\'s Book Supply': 'bottom_minus_ship',
        'Liberty Mountain Sports': 'bottom_minus_ship',
        
        # Label detection approach vendors (100% success)
        'Badfish': 'label',
        
        # Label minus shipping approach vendors (100% success)
        'Accent & Cannon': 'label_minus_ship',
        'Cotopaxi': 'label_minus_ship', 
        'Hoka': 'label_minus_ship',
        'Katin': 'label_minus_ship',
        'Loksak': 'label_minus_ship',
        'Vuori': 'label_minus_ship',
    }
    
    # --- 3-TIER FALLBACK SYSTEM ---
    
    # TIER 1: Vendor-specific approach (for 100% success vendors)
    preferred_approach = VENDOR_APPROACH_MAP.get(vendor_name)
    
    if preferred_approach == 'gross':
        result = _extract_gross_amount(words, vendor_name)
        if result: return result
    elif preferred_approach == 'calculated':
        gross_amount = _extract_gross_amount(words, vendor_name)
        if gross_amount:
            result = _apply_calculated_adjustment(gross_amount, words, vendor_name)
            if result: return result
        if gross_amount: return gross_amount
    elif preferred_approach == 'bottom_most':
        result = extract_bottom_most_currency(words, vendor_name)
        if result: return result
    elif preferred_approach == 'bottom_minus_ship':
        shipping_cost = _extract_shipping_cost(words, vendor_name)
        result = extract_bottom_most_minus_shipping(words, vendor_name, shipping_cost)
        if result: return result
    elif preferred_approach == 'label':
        result = _extract_with_label_fallback(words, vendor_name)
        if result: return result
    elif preferred_approach == 'label_minus_ship':
        result = extract_label_minus_shipping(words, vendor_name)
        if result: return result
    
    # TIER 2: Label-based fallback (for failed cases)
    #print(f"[TOTAL_DEBUG] {vendor_name}: Trying label-based fallback")
    label_result = _extract_with_label_fallback(words, vendor_name)
    if label_result:
        #print(f"[TOTAL_DEBUG] {vendor_name}: Label fallback succeeded: {label_result}")
        return label_result
    #print(f"[TOTAL_DEBUG] {vendor_name}: Label fallback failed, trying general logic")
    
    # TIER 3: Original logic fallback

     # --- Currency pattern ---
    amount_pattern = r'^-?\$?-?(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}$T?'

    def is_currency(text):
        value = preprocess_currency_text(text.strip())
        return re.match(amount_pattern, value) is not None

    # --- ON Running special-case ---
    if vendor_name == "ON Running":
        #print(f"[DEBUG] Special-case vendor detected: {vendor_name} (searching lowest 'Total')")

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
                    #print(f"[DEBUG] Selected ON Running amount: {value} → {amount:.2f}")
                    return f"{amount:.2f}"
                except Exception:
                    #print(f"[DEBUG] Failed to convert '{value}' to float for ON Running")
                    pass

        #print("[DEBUG] ON Running special-case failed, falling back to general logic.")

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
        #print(f"[DEBUG] Special-case vendor detected: {vendor_name} (label: {label})")
        # Use find_label_positions to find the label
        label_positions = find_label_positions(normalized_words, label_type=None, custom_label=label)
        #print(f"[DEBUG] Found {len(label_positions)} label positions for '{label}'")
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
                #print(f"[DEBUG] Selected special-case amount: {value} → {amount:.2f}")
                return f"{amount:.2f}"
            except Exception:
                #print(f"[DEBUG] Failed to convert '{value}' to float")
                pass
        #print("[DEBUG] Special-case label found, but no valid value to right. Falling back to general logic.")

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
                #print(f"[TOTAL_DEBUG] {vendor_name}: Found candidate amount: {value} → {amount:.2f}")
            except ValueError:
                continue

    if not candidates:
        #print(f"[TOTAL_DEBUG] {vendor_name}: No valid currency amounts found")
        return ""

    #print(f"[TOTAL_DEBUG] {vendor_name}: Found {len(candidates)} total candidates")
    
    # Find the amount with largest absolute value
    largest_abs = max(candidates, key=lambda x: abs(x['amount']))

    # Check if there's a negative amount with the same absolute value
    negative_match = next(
        (x for x in candidates if abs(x['amount']) == abs(largest_abs['amount']) and x['amount'] < 0),
        None
    )

    # Prefer negative amount if it exists with same absolute value
    result = negative_match if negative_match else largest_abs
    #print(f"[TOTAL_DEBUG] {vendor_name}: Selected amount: {result['raw']} → {result['amount']:.2f}")

    return f"{result['amount']:.2f}"

def extract_bottom_most_currency(words, vendor_name):
    """Extract the currency amount that appears lowest on the page (highest Y-coordinate)."""
    amount_pattern = r'^-?\$?-?(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}$T?'
    
    def is_currency(text):
        value = preprocess_currency_text(text.strip())
        return re.match(amount_pattern, value) is not None
    
    # Collect all currency candidates with their position data
    candidates = []
    for word in words:
        if is_currency(word["text"]):
            value = preprocess_currency_text(word["text"].strip())
            cleaned = clean_currency(value)
            try:
                amount = float(cleaned)
                candidates.append({
                    'raw': word["text"],
                    'amount': amount,
                    'page_num': word.get("page_num", 0),
                    'y_position': word.get("top", 0)  # Y-coordinate on page
                })
            except ValueError:
                continue
    
    if not candidates:
        return ""
    
    # Find the candidate with the highest Y-coordinate (lowest on page)
    # Sort by page number first, then by Y-position (descending for lowest position)
    bottom_most = max(candidates, key=lambda x: (x['page_num'], x['y_position']))
    
    return f"{bottom_most['amount']:.2f}"

def extract_bottom_most_minus_shipping(words, vendor_name, shipping_cost_str):
    """Extract the bottom-most currency amount and subtract shipping cost."""
    bottom_most_amount = extract_bottom_most_currency(words, vendor_name)
    
    if not bottom_most_amount:
        return ""
    
    try:
        bottom_most_value = float(bottom_most_amount)
        shipping_cost = float(str(shipping_cost_str).replace(',', '')) if shipping_cost_str else 0.0
        
        adjusted_amount = bottom_most_value - shipping_cost
        return f"{adjusted_amount:.2f}"
    except (ValueError, TypeError):
        return bottom_most_amount  # Return original if calculation fails

def _extract_gross_amount(words, vendor_name):
    """Extract using the original gross amount logic."""
    # This is the original extract_total_amount logic
    amount_pattern = r'^-?\$?-?(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}$T?'

    def is_currency(text):
        value = preprocess_currency_text(text.strip())
        return re.match(amount_pattern, value) is not None

    # --- ON Running special-case ---
    if vendor_name == "ON Running":
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
                    return f"{amount:.2f}"
                except Exception:
                    pass

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
        label_positions = find_label_positions(normalized_words, label_type=None, custom_label=label)
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
                return f"{amount:.2f}"
            except Exception:
                pass

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
            except ValueError:
                continue

    if not candidates:
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

    return f"{result['amount']:.2f}"

def _apply_calculated_adjustment(gross_amount, words, vendor_name):
    """Apply discount and shipping adjustments to gross amount."""
    try:
        total_amount = float(gross_amount.replace(',', ''))
        
        # Get shipping cost
        shipping_cost = float(_extract_shipping_cost(words, vendor_name).replace(',', '')) if _extract_shipping_cost(words, vendor_name) else 0.0
        
        # Get discount terms
        discount_terms = _extract_discount_terms(words, vendor_name).strip()
        
        # Subtract shipping cost
        net_amount = total_amount - shipping_cost
        
        # Parse discount percentage if present
        discount_rate = 0.0
        if discount_terms and '%' in discount_terms:
            import re
            discount_match = re.search(r'(\d+(?:\.\d+)?)%', discount_terms)
            if discount_match:
                discount_rate = float(discount_match.group(1)) / 100.0
        
        # Apply discount
        adjusted_amount = net_amount * (1 - discount_rate)
        
        return f"{adjusted_amount:.2f}"
        
    except (ValueError, TypeError):
        return gross_amount  # Return original if calculation fails

def _extract_shipping_cost(words, vendor_name):
    """Extract shipping cost using the shipping cost extractor."""
    try:
        from .shipping_cost import extract_shipping_cost
        result = extract_shipping_cost(words, vendor_name)
        return result if result else ""
    except ImportError:
        return ""

def _extract_discount_terms(words, vendor_name):
    """Extract discount terms using the discount terms extractor."""
    try:
        from .discount_terms import extract_discount_terms
        result = extract_discount_terms(words, vendor_name)
        return result if result else ""
    except ImportError:
        return ""

def extract_label_minus_shipping(words, vendor_name):
    """Extract using label detection, then subtract shipping cost."""
    label_result = _extract_with_label_fallback(words, vendor_name)
    if not label_result:
        return ""
    
    shipping_cost = _extract_shipping_cost(words, vendor_name) 
    if not shipping_cost:
        return label_result  # Return label result if no shipping
    
    try:
        label_amount = float(label_result)
        ship_amount = float(shipping_cost.replace('$', '').replace(',', ''))
        result = label_amount - ship_amount
        return f"{result:.2f}"
    except (ValueError, TypeError):
        return label_result  # Fallback to label result

def _extract_with_label_fallback(words, vendor_name):
    """TIER 2: Try to extract using common total/balance labels."""
    
    # Common labels that might indicate the final amount
    fallback_labels = [
        # High priority exact matches
        'balance due', 'amount due', 'total due', 'payment due',
        'net amount', 'net total', 'subtotal',
        
        # Medium priority compound labels  
        'final amount', 'amount owed', 'outstanding', 'amount to pay',
        'remaining amount', 'current balance', 'total amount', 
        'invoice total', 'pay amount', 'amount payable',
        
        # Single word labels (lower priority)
        'balance', 'total', 'due', 'subtotal', 'amount'
    ]
    
    # Currency pattern for validation
    amount_pattern = r'^-?\$?-?(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}$T?'
    
    def is_currency(text):
        value = preprocess_currency_text(text.strip())
        return re.match(amount_pattern, value) is not None
    
    # Search for labels and nearby currency values
    candidates = []
    
    # Build combined text phrases for better multi-word label matching
    word_phrases = []
    for i, word in enumerate(words):
        # Single word
        single_phrase = {
            'text': word.get('text', '').lower().strip(),
            'words': [word],
            'start_x': word.get('x0', 0),
            'end_x': word.get('x1', 0),
            'y': word.get('top', 0),
            'page': word.get('page_num', 0)
        }
        word_phrases.append(single_phrase)
        
        # Two-word combination
        if i + 1 < len(words):
            next_word = words[i + 1]
            if (abs(next_word.get('top', 0) - word.get('top', 0)) <= 10 and  # Same line
                next_word.get('x0', 0) - word.get('x1', 0) <= 50):  # Reasonable spacing
                combined_text = f"{single_phrase['text']} {next_word.get('text', '').lower().strip()}"
                two_word_phrase = {
                    'text': combined_text,
                    'words': [word, next_word],
                    'start_x': word.get('x0', 0),
                    'end_x': next_word.get('x1', 0),
                    'y': word.get('top', 0),
                    'page': word.get('page_num', 0)
                }
                word_phrases.append(two_word_phrase)
    
    # Check each phrase against our labels
    for phrase in word_phrases:
        phrase_text = phrase['text']
        
        # Check if this phrase matches any of our fallback labels
        for label in fallback_labels:
            # Exact match or phrase contains the label
            if (label == phrase_text or 
                (len(label.split()) == 1 and label in phrase_text.split()) or
                (len(label.split()) > 1 and label in phrase_text)):
                # Found a potential label, look for currency values to the right
                for candidate_word in words:
                    if (candidate_word.get('page_num', 0) == phrase['page'] and
                        abs(candidate_word.get('top', 0) - phrase['y']) <= 15 and  # Same line or close
                        candidate_word.get('x0', 0) > phrase['end_x']):  # To the right
                        
                        candidate_text = candidate_word.get('text', '').strip()
                        if is_currency(candidate_text):
                            try:
                                cleaned = clean_currency(preprocess_currency_text(candidate_text))
                                amount = float(cleaned)
                                candidates.append({
                                    'label': label,
                                    'raw_text': candidate_text,
                                    'amount': amount,
                                    'x_pos': candidate_word.get('x0', 0),
                                    'y_pos': candidate_word.get('top', 0)
                                })
                            except (ValueError, TypeError):
                                continue
    
    if not candidates:
        return ""
    
    # Prefer certain labels over others
    label_priority = {
        # High priority - most specific
        'balance due': 1,
        'amount due': 2, 
        'total due': 3,
        'payment due': 4,
        
        # Medium-high priority - compound labels
        'net amount': 5,
        'net total': 6,
        'final amount': 7,
        'amount to pay': 8,
        'total amount': 9,
        'invoice total': 10,
        'amount payable': 11,
        
        # Medium priority
        'outstanding': 12,
        'remaining amount': 13,
        'current balance': 14,
        'pay amount': 15,
        'subtotal': 16,
        
        # Lower priority - single words (can be ambiguous)
        'balance': 20,
        'total': 21,
        'due': 22,
        'amount': 23
    }
    
    # Sort by label priority, then by position (rightmost, then bottommost)
    candidates.sort(key=lambda x: (
        label_priority.get(x['label'], 99),  # Priority first
        -x['x_pos'],  # Rightmost first (negative for descending)
        -x['y_pos']   # Bottommost first
    ))
    
    # Return the best candidate
    best_candidate = candidates[0]
    return f"{best_candidate['amount']:.2f}"

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