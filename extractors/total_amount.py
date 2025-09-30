import re
import string
import csv
import os
from decimal import Decimal, ROUND_HALF_UP
from .common_extraction import normalize_words, find_label_positions, find_value_to_right
from .utils import clean_currency
from logging_config import get_logger

logger = get_logger(__name__)

# Special vendor label mappings for label-based extraction
SPECIAL_VENDOR_LABELS = {
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
    "Simms": "total amt due",
}

def _load_vendor_approach_map():
    """Load vendor approach mapping from CSV file."""
    vendor_map = {}
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'vendor_approach_map.csv')

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                vendor_map[row['vendor_name']] = row['approach']
        logger.info(f"Loaded {len(vendor_map)} vendor approach mappings from CSV")
    except Exception as e:
        logger.error(f"Failed to load vendor approach map: {e}")
        # Fallback to empty dict - will use general logic
        vendor_map = {}

    return vendor_map

def format_currency(amount):
    """Format amount to 2 decimal places using proper currency rounding (round half up)."""
    if isinstance(amount, str):
        amount = float(amount)
    # Convert to Decimal for precise rounding, then back to string
    decimal_amount = Decimal(str(amount))
    rounded = decimal_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    return str(rounded)

# Comprehensive currency pattern that supports:
# - Regular: 123.45, $123.45, 1,234.56
# - Negative: -123.45, -$123.45, $-123.45
# - Parentheses: (123.45), ($123.45), $(123.45)
CURRENCY_PATTERN = r'^(?:-?\$?-?(?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}|\$?\((?:\d{1,3}(?:,\d{3})*|\d+)\.\d{2}\))$T?'

def is_currency(text):
    """Check if text matches currency format (including parentheses for negative amounts)."""
    original_text = text.strip()
    preprocessed_text = preprocess_currency_text(original_text)
    # Check both original and preprocessed text to handle parentheses format
    return (re.match(CURRENCY_PATTERN, original_text) is not None or
            re.match(CURRENCY_PATTERN, preprocessed_text) is not None)

# Load vendor approach mapping from CSV file
VENDOR_APPROACH_MAP = _load_vendor_approach_map()

def _apply_credit_memo_logic(amount_str, words, vendor_name):
    """Apply credit memo/note logic to ensure negative amounts for credit documents."""
    if not amount_str:
        return amount_str

    # Check if this is a credit document
    discount_terms = _extract_discount_terms(words, vendor_name).lower()
    if ('credit memo' in discount_terms or 'credit note' in discount_terms or 'product return' in discount_terms or 'return authorization' in discount_terms or 'ra for credit' in discount_terms):
        try:
            # Handle parentheses format (238.95) for credit memos
            if amount_str.startswith('(') and amount_str.endswith(')'):
                # Extract the amount inside parentheses and make it negative
                inner_amount = amount_str[1:-1].strip()
                amount_value = float(inner_amount)
                return f"-{format_currency(amount_value)}"
            else:
                # Regular format - make positive amounts negative, keep negative amounts as-is
                amount_value = float(amount_str)
                if amount_value > 0:
                    return f"-{format_currency(amount_value)}"
                else:
                    # Already negative, keep as-is for credit documents
                    return format_currency(amount_value)
        except ValueError:
            pass

    # If we have a negative amount but it's NOT a credit document, default to 0
    # This handles cases where invoices are paid by credits/discounts but not properly labeled
    try:
        amount_value = float(amount_str)
        if amount_value < 0:
            # Not a credit document but amount is negative - likely fully paid by credits
            return "0.00"
    except (ValueError, TypeError):
        pass

    return amount_str

def _create_result(total_amount, calculation_method='gross', discount_type='none',
                  discount_value=None, pre_discount_amount=None):
    """Create enhanced result dict with calculation details."""
    if not total_amount:
        return {
            'total_amount': '',
            'calculation_method': 'none',
            'discount_type': 'none',
            'discount_value': None,
            'pre_discount_amount': None,
            'has_calculation': False
        }

    return {
        'total_amount': total_amount,
        'calculation_method': calculation_method,
        'discount_type': discount_type,
        'discount_value': discount_value,
        'pre_discount_amount': pre_discount_amount,
        'has_calculation': discount_type != 'none'
    }

def _extract_percentage_from_terms(discount_terms):
    """Extract percentage value from discount terms."""
    if not discount_terms or '%' not in discount_terms:
        return None

    import re
    discount_match = re.search(r'(\d+(?:\.\d+)?)%', discount_terms)
    return discount_match.group(1) if discount_match else None

def extract_total_amount(words, vendor_name):
    """Extract the total amount from OCR words, returns enhanced calculation data."""


    # --- 3-TIER FALLBACK SYSTEM ---

    # TIER 1: Vendor-specific approach (for 100% success vendors)
    preferred_approach = VENDOR_APPROACH_MAP.get(vendor_name)

    
    if preferred_approach == 'gross':
        result = _extract_gross_amount(words, vendor_name)
        if result:
            final_amount = _apply_credit_memo_logic(result, words, vendor_name)
            return _create_result(final_amount, 'gross')
    elif preferred_approach == 'calculated':
        gross_amount = _extract_gross_amount(words, vendor_name)
        if gross_amount:
            result_data = _apply_calculated_adjustment_enhanced(gross_amount, words, vendor_name)
            if result_data['total_amount']:
                final_amount = _apply_credit_memo_logic(result_data['total_amount'], words, vendor_name)
                result_data['total_amount'] = final_amount
                return result_data
        if gross_amount:
            final_amount = _apply_credit_memo_logic(gross_amount, words, vendor_name)
            return _create_result(final_amount, 'gross')
    elif preferred_approach == 'bottom_most':
        result = extract_bottom_most_currency(words, vendor_name)
        if result:
            final_amount = _apply_credit_memo_logic(result, words, vendor_name)
            return _create_result(final_amount, 'bottom_most')
    elif preferred_approach == 'bottom_minus_ship':
        shipping_cost = _extract_shipping_cost(words, vendor_name)
        result = extract_bottom_most_minus_shipping(words, vendor_name, shipping_cost)
        if result:
            final_amount = _apply_credit_memo_logic(result, words, vendor_name)
            return _create_result(final_amount, 'bottom_minus_ship')
    elif preferred_approach == 'label':
        result = _extract_with_label_fallback(words, vendor_name)
        if result:
            final_amount = _apply_credit_memo_logic(result, words, vendor_name)
            return _create_result(final_amount, 'label')
    elif preferred_approach == 'label_minus_ship':
        result = extract_label_minus_shipping(words, vendor_name)
        if result:
            final_amount = _apply_credit_memo_logic(result, words, vendor_name)
            return _create_result(final_amount, 'label_minus_ship')
    elif preferred_approach == 'label_calculated':
        label_amount = _extract_with_label_fallback(words, vendor_name)
        if label_amount:
            result_data = _apply_calculated_adjustment_enhanced(label_amount, words, vendor_name)
            if result_data['total_amount']:
                final_amount = _apply_credit_memo_logic(result_data['total_amount'], words, vendor_name)
                result_data['total_amount'] = final_amount
                result_data['calculation_method'] = 'label_calculated'
                return result_data
        if label_amount:
            final_amount = _apply_credit_memo_logic(label_amount, words, vendor_name)
            return _create_result(final_amount, 'label')
    elif preferred_approach == 'bottom_calculated':
        bottom_amount = extract_bottom_most_currency(words, vendor_name)
        if bottom_amount:
            result_data = _apply_calculated_adjustment_enhanced(bottom_amount, words, vendor_name)
            if result_data['total_amount']:
                final_amount = _apply_credit_memo_logic(result_data['total_amount'], words, vendor_name)
                result_data['total_amount'] = final_amount
                result_data['calculation_method'] = 'bottom_calculated'
                return result_data
        if bottom_amount:
            final_amount = _apply_credit_memo_logic(bottom_amount, words, vendor_name)
            return _create_result(final_amount, 'bottom_most')
    elif preferred_approach == 'second_from_bottom':
        result = extract_second_from_bottom_currency(words, vendor_name)
        if result:
            final_amount = _apply_credit_memo_logic(result, words, vendor_name)
            return _create_result(final_amount, 'second_from_bottom')
    elif preferred_approach == 'second_from_bottom_minus_ship':
        shipping_cost = _extract_shipping_cost(words, vendor_name)
        result = extract_second_from_bottom_minus_shipping(words, vendor_name, shipping_cost)
        if result:
            final_amount = _apply_credit_memo_logic(result, words, vendor_name)
            return _create_result(final_amount, 'second_from_bottom_minus_ship')
    elif preferred_approach == 'subtotal_minus_discount':
        result_data = extract_subtotal_minus_discount_enhanced(words, vendor_name)
        if result_data['total_amount']:
            final_amount = _apply_credit_memo_logic(result_data['total_amount'], words, vendor_name)
            result_data['total_amount'] = final_amount
            return result_data
    elif preferred_approach == 'gross_calculated':
        gross_amount = _extract_gross_amount(words, vendor_name)
        if gross_amount:
            result_data = _apply_calculated_adjustment_enhanced(gross_amount, words, vendor_name)
            if result_data['total_amount']:
                final_amount = _apply_credit_memo_logic(result_data['total_amount'], words, vendor_name)
                result_data['total_amount'] = final_amount
                result_data['calculation_method'] = 'gross_calculated'
                return result_data
        if gross_amount:
            final_amount = _apply_credit_memo_logic(gross_amount, words, vendor_name)
            return _create_result(final_amount, 'gross')
        return _create_result('', 'none')

    # TIER 2: Label-based fallback (for failed cases)
    if vendor_name == "Simms":
        logger.debug("Simms reached TIER 2: Label-based fallback")
    label_result = _extract_with_label_fallback(words, vendor_name)
    if vendor_name == "Simms":
        logger.debug(f"Simms TIER 2 label_result: '{label_result}'")
    if label_result:
        if vendor_name == "Simms":
            logger.debug(f"Simms TIER 2 label fallback succeeded: {label_result}")
        final_amount = _apply_credit_memo_logic(label_result, words, vendor_name)
        return _create_result(final_amount, 'label_fallback')
    #print(f"[TOTAL_DEBUG] {vendor_name}: Label fallback failed, trying general logic")
    
    # TIER 3: Original logic fallback
    if vendor_name == "Simms":
        logger.debug("Simms reached TIER 3: Original logic fallback")

    # Use centralized currency detection

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
                    #print(f"[DEBUG] Selected ON Running amount: {value} → {format_currency(amount)}")
                    return _apply_credit_memo_logic(format_currency(amount), words, vendor_name)
                except Exception:
                    #print(f"[DEBUG] Failed to convert '{value}' to float for ON Running")
                    pass

        #print("[DEBUG] ON Running special-case failed, falling back to general logic.")

    # --- Special-case vendor/label mapping ---
    label = SPECIAL_VENDOR_LABELS.get(vendor_name)

    normalized_words = normalize_words(words, first_page_only=True)

    # --- Special-case logic ---
    if label:
        if vendor_name == "Simms":
            logger.debug(f"Simms special-case vendor detected with label: '{label}'")
        # Use find_label_positions to find the label
        label_positions = find_label_positions(normalized_words, label_type=None, custom_label=label)
        if vendor_name == "Simms":
            logger.debug(f"Simms found {len(label_positions)} label positions for '{label}'")
        # Use find_value_to_right to find the first valid currency value to the right
        if vendor_name == "Simms":
            # Debug: Show all currency values near the label
            for label_pos in label_positions:
                logger.debug(f"Simms label position: x0:{label_pos.get('x0', 0)}, x1:{label_pos.get('x1', 0)}, top:{label_pos.get('top', 0)}")
                nearby_currencies = []
                for word in normalized_words:
                    if is_currency(word["text"]):
                        distance = word.get("x0", 0) - label_pos.get("x1", 0)
                        v_distance = abs(word.get("top", 0) - label_pos.get("top", 0))
                        nearby_currencies.append({
                            'text': word["text"],
                            'x0': word.get("x0", 0),
                            'top': word.get("top", 0),
                            'h_distance': distance,
                            'v_distance': v_distance
                        })
                logger.debug("Simms nearby currencies:")
                for curr in sorted(nearby_currencies, key=lambda x: x['h_distance']):
                    logger.debug(f"  '{curr['text']}' at x0:{curr['x0']}, top:{curr['top']} | h_dist:{curr['h_distance']:.1f}, v_dist:{curr['v_distance']:.1f}")

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
                if vendor_name == "Simms":
                    logger.debug(f"Simms selected special-case amount: '{value}' → ${format_currency(amount)}")
                return _apply_credit_memo_logic(format_currency(amount), words, vendor_name)
            except Exception:
                if vendor_name == "Simms":
                    logger.debug(f"Simms failed to convert '{value}' to float")
                pass
        else:
            if vendor_name == "Simms":
                logger.debug("Simms special-case label found, but no valid value to right. Falling back to general logic.")

    # --- General logic (existing) ---
    candidates = []
    for word in words:
        value = word["text"].strip()
        value = preprocess_currency_text(value)
        if is_currency(value):
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
        return _create_result('', 'none')

    #print(f"[TOTAL_DEBUG] {vendor_name}: Found {len(candidates)} total candidates")

    # Johnson Outdoors special case: filter out $50.00 candidates
    if vendor_name == "Johnson Outdoors":
        original_count = len(candidates)
        candidates = [c for c in candidates if abs(c['amount']) != 50.0]
        if len(candidates) != original_count:
            #print(f"[DEBUG] Johnson Outdoors: Filtered out {original_count - len(candidates)} $50.00 candidates")
            pass

    if not candidates:
        #print(f"[TOTAL_DEBUG] {vendor_name}: No valid currency amounts found after filtering")
        return _create_result('', 'none')

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

    final_amount = format_currency(result['amount'])
    final_amount = _apply_credit_memo_logic(final_amount, words, vendor_name)
    return _create_result(final_amount, 'general_fallback')

def get_total_amount_string(words, vendor_name):
    """Backward compatibility function that returns just the total amount string."""
    result = extract_total_amount(words, vendor_name)
    return result.get('total_amount', '') if isinstance(result, dict) else str(result)

def extract_bottom_most_currency(words, vendor_name):
    """Extract the currency amount that appears lowest on the page (highest Y-coordinate).
    If multiple values exist at the same bottom Y-position, take the rightmost one."""

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
                    'y_position': word.get("top", 0),  # Y-coordinate on page
                    'x_position': word.get("x0", 0)   # X-coordinate for rightmost selection
                })
            except ValueError:
                continue

    if not candidates:
        return ""

    # Find the bottom-most Y-position on the last page
    max_page = max(candidates, key=lambda x: x['page_num'])['page_num']
    page_candidates = [c for c in candidates if c['page_num'] == max_page]
    max_y = max(page_candidates, key=lambda x: x['y_position'])['y_position']

    # Get all candidates at the bottom-most Y-position
    bottom_candidates = [c for c in page_candidates if c['y_position'] == max_y]

    # If multiple candidates at same Y-position, take the rightmost one
    if len(bottom_candidates) > 1:
        bottom_most = max(bottom_candidates, key=lambda x: x['x_position'])
    else:
        bottom_most = bottom_candidates[0]

    return format_currency(bottom_most['amount'])

def extract_second_from_bottom_currency(words, vendor_name):
    """Extract the currency amount that appears second-to-lowest on the page (second highest Y-coordinate).
    If multiple values exist at the same Y-position, take the rightmost one."""

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
                    'y_position': word.get("top", 0),  # Y-coordinate on page
                    'x_position': word.get("x0", 0)   # X-coordinate for rightmost selection
                })
            except ValueError:
                continue

    if len(candidates) < 2:
        # If less than 2 candidates, fall back to bottom-most
        return extract_bottom_most_currency(words, vendor_name)

    # Find unique Y-positions on the last page, sorted from bottom to top
    max_page = max(candidates, key=lambda x: x['page_num'])['page_num']
    page_candidates = [c for c in candidates if c['page_num'] == max_page]
    unique_y_positions = sorted(set(c['y_position'] for c in page_candidates), reverse=True)

    # If we don't have at least 2 distinct Y-positions, fall back to bottom-most
    if len(unique_y_positions) < 2:
        return extract_bottom_most_currency(words, vendor_name)

    # Get the second Y-position from bottom
    second_y = unique_y_positions[1]

    # Get all candidates at the second Y-position
    second_candidates = [c for c in page_candidates if c['y_position'] == second_y]

    # If multiple candidates at same Y-position, take the rightmost one
    if len(second_candidates) > 1:
        second_from_bottom = max(second_candidates, key=lambda x: x['x_position'])
    else:
        second_from_bottom = second_candidates[0]

    return format_currency(second_from_bottom['amount'])

def extract_bottom_most_minus_shipping(words, vendor_name, shipping_cost_str):
    """Extract the bottom-most currency amount and subtract shipping cost."""
    bottom_most_amount = extract_bottom_most_currency(words, vendor_name)

    if not bottom_most_amount:
        return ""

    try:
        bottom_most_value = float(bottom_most_amount)
        shipping_cost = float(str(shipping_cost_str).replace(',', '')) if shipping_cost_str else 0.0

        adjusted_amount = bottom_most_value - shipping_cost
        return format_currency(adjusted_amount)
    except (ValueError, TypeError):
        return bottom_most_amount  # Return original if calculation fails

def extract_second_from_bottom_minus_shipping(words, vendor_name, shipping_cost_str):
    """Extract the second-from-bottom currency amount and subtract shipping cost."""
    second_from_bottom_amount = extract_second_from_bottom_currency(words, vendor_name)

    if not second_from_bottom_amount:
        return ""

    try:
        second_from_bottom_value = float(second_from_bottom_amount)
        shipping_cost = float(str(shipping_cost_str).replace(',', '')) if shipping_cost_str else 0.0

        adjusted_amount = second_from_bottom_value - shipping_cost
        return format_currency(adjusted_amount)
    except (ValueError, TypeError):
        return second_from_bottom_amount  # Return original if calculation fails

def extract_subtotal_minus_discount(words, vendor_name):
    """Extract subtotal value and subtract any currency value found below it (for Rio Products)."""
    from .common_extraction import normalize_words

    normalized_words = normalize_words(words, first_page_only=False)

    if not normalized_words:
        return ""


    # Find "subtotal" label positions
    subtotal_positions = []

    for word in normalized_words:
        word_text = word["text"].lower().rstrip(":")

        if word_text == "subtotal":
            pos_data = {
                "x0": word["x0"],
                "x1": word["x1"],
                "top": word["top"],
                "bottom": word["bottom"],
                "label": word["text"],
                "page_num": word["page_num"]
            }
            subtotal_positions.append(pos_data)

    # Find subtotal values and potential discounts below them
    for label_pos in subtotal_positions:
        label_page = label_pos.get("page_num", 0)

        # Find subtotal value (to the right or below the label)
        subtotal_candidates = []
        discount_candidates = []

        for word in normalized_words:
            word_page = word.get("page_num", 0)

            # Skip if they're on different pages
            if label_page != word_page:
                continue

            if is_currency(word["text"]):
                # Check distances for Rio Products subtotal detection
                horizontal_distance = word["x0"] - label_pos["x1"]
                vertical_alignment = abs(word["top"] - label_pos["top"])
                vertical_distance = word["top"] - label_pos["bottom"]


                # Check if this currency is on the same line as the subtotal label
                if (vertical_distance >= -5 and vertical_distance <= 15 and  # Same line as label (±15px)
                    abs(horizontal_distance) <= 200):                       # Horizontally reasonable range

                    value = preprocess_currency_text(word["text"].strip())
                    cleaned = clean_currency(value)
                    try:
                        amount = float(cleaned)
                        subtotal_candidates.append({
                            'amount': amount,
                            'y_position': word["top"],
                            'x_position': word["x0"],
                            'v_distance': vertical_distance
                        })
                    except ValueError:
                        continue

                # Check if this currency is on a different line (discount candidate)
                elif vertical_distance > 15:  # Different line from label
                    value = preprocess_currency_text(word["text"].strip())
                    cleaned = clean_currency(value)
                    try:
                        amount = float(cleaned)
                        discount_candidates.append({
                            'amount': amount,
                            'y_position': word["top"]
                        })
                    except ValueError:
                        continue

        # Process if we found a subtotal
        if subtotal_candidates:
            # Take the leftmost subtotal candidate (smallest x-position)
            leftmost_subtotal = min(subtotal_candidates, key=lambda x: x['x_position'])
            subtotal_amount = leftmost_subtotal['amount']

            # Find the discount (lowest Y-position = furthest down)
            if discount_candidates:
                # Sort by Y-position descending (highest Y = lowest on page)
                discount_candidates.sort(key=lambda x: x['y_position'], reverse=True)
                discount_amount = discount_candidates[0]['amount']

                # Calculate final amount: subtotal - discount
                final_amount = subtotal_amount - discount_amount
                return format_currency(final_amount)
            else:
                # No discount found, return subtotal as-is
                return format_currency(subtotal_amount)

    return ""

def extract_subtotal_minus_discount_enhanced(words, vendor_name):
    """Enhanced version of extract_subtotal_minus_discount that returns calculation details."""
    from .common_extraction import normalize_words

    normalized_words = normalize_words(words, first_page_only=False)

    if not normalized_words:
        return _create_result('', 'none')

    # Find "subtotal" label positions
    subtotal_positions = []

    for word in normalized_words:
        word_text = word["text"].lower().rstrip(":")

        if word_text == "subtotal":
            pos_data = {
                "x0": word["x0"],
                "x1": word["x1"],
                "top": word["top"],
                "bottom": word["bottom"],
                "label": word["text"],
                "page_num": word["page_num"]
            }
            subtotal_positions.append(pos_data)

    # Find subtotal values and potential discounts below them
    for label_pos in subtotal_positions:
        label_page = label_pos.get("page_num", 0)

        # Find subtotal value (to the right or below the label)
        subtotal_candidates = []
        discount_candidates = []

        for word in normalized_words:
            word_page = word.get("page_num", 0)

            # Skip if they're on different pages
            if label_page != word_page:
                continue

            if is_currency(word["text"]):
                # Check distances for Rio Products subtotal detection
                horizontal_distance = word["x0"] - label_pos["x1"]
                vertical_alignment = abs(word["top"] - label_pos["top"])
                vertical_distance = word["top"] - label_pos["bottom"]

                # Check if this currency is on the same line as the subtotal label
                if (vertical_distance >= -5 and vertical_distance <= 15 and  # Same line as label (±15px)
                    abs(horizontal_distance) <= 200):                       # Horizontally reasonable range

                    value = preprocess_currency_text(word["text"].strip())
                    cleaned = clean_currency(value)
                    try:
                        amount = float(cleaned)
                        subtotal_candidates.append({
                            'amount': amount,
                            'y_position': word["top"],
                            'x_position': word["x0"],
                            'v_distance': vertical_distance
                        })
                    except ValueError:
                        continue

                # Check if this currency is on a different line (discount candidate)
                elif vertical_distance > 15:  # Different line from label
                    value = preprocess_currency_text(word["text"].strip())
                    cleaned = clean_currency(value)
                    try:
                        amount = float(cleaned)
                        discount_candidates.append({
                            'amount': amount,
                            'y_position': word["top"]
                        })
                    except ValueError:
                        continue

        # Process if we found a subtotal
        if subtotal_candidates:
            # Take the leftmost subtotal candidate (smallest x-position)
            leftmost_subtotal = min(subtotal_candidates, key=lambda x: x['x_position'])
            subtotal_amount = leftmost_subtotal['amount']

            # Find the discount (lowest Y-position = furthest down)
            if discount_candidates:
                # Sort by Y-position descending (highest Y = lowest on page)
                discount_candidates.sort(key=lambda x: x['y_position'], reverse=True)
                discount_amount = discount_candidates[0]['amount']

                # Calculate final amount: subtotal - discount
                final_amount = subtotal_amount - discount_amount

                return _create_result(
                    total_amount=format_currency(final_amount),
                    calculation_method='subtotal_minus_discount',
                    discount_type='dollar',
                    discount_value=format_currency(discount_amount),
                    pre_discount_amount=format_currency(subtotal_amount)
                )
            else:
                # No discount found, return subtotal as-is
                return _create_result(
                    total_amount=format_currency(subtotal_amount),
                    calculation_method='subtotal_minus_discount'
                )

    return _create_result('', 'none')

def _extract_gross_amount(words, vendor_name):
    """Extract using the original gross amount logic."""
    # This is the original extract_total_amount logic

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
                    return format_currency(amount)
                except Exception:
                    pass

    # --- Special-case vendor/label mapping ---
    label = SPECIAL_VENDOR_LABELS.get(vendor_name)
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
                return format_currency(amount)
            except Exception:
                pass

    # --- General logic (existing) ---
    candidates = []
    for word in words:
        value = word["text"].strip()
        value = preprocess_currency_text(value)
        if is_currency(value):
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

    # Johnson Outdoors special case: filter out $50.00 candidates
    if vendor_name == "Johnson Outdoors":
        original_count = len(candidates)
        candidates = [c for c in candidates if abs(c['amount']) != 50.0]
        if len(candidates) != original_count:
            #print(f"[DEBUG] Johnson Outdoors: Filtered out {original_count - len(candidates)} $50.00 candidates")
            pass

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

    return format_currency(result['amount'])

def _apply_calculated_adjustment(gross_amount, words, vendor_name):
    """Apply discount and shipping adjustments to gross amount."""
    try:
        # Use Decimal for precise calculations to avoid floating-point precision issues
        total_amount = Decimal(gross_amount.replace(',', ''))

        # Get shipping cost
        shipping_cost_str = _extract_shipping_cost(words, vendor_name)
        shipping_cost = Decimal(shipping_cost_str.replace(',', '')) if shipping_cost_str else Decimal('0.0')

        # Get discount terms using standard extraction
        discount_terms = _extract_discount_terms(words, vendor_name).strip()

        # Subtract shipping cost
        net_amount = total_amount - shipping_cost

        # Parse discount percentage if present
        discount_rate = Decimal('0.0')
        if discount_terms and '%' in discount_terms:
            import re
            discount_match = re.search(r'(\d+(?:\.\d+)?)%', discount_terms)
            if discount_match:
                discount_rate = Decimal(discount_match.group(1)) / Decimal('100.0')

        # Apply discount using Decimal arithmetic
        adjusted_amount = net_amount * (Decimal('1.0') - discount_rate)

        return format_currency(float(adjusted_amount))

    except (ValueError, TypeError):
        return gross_amount  # Return original if calculation fails

def _apply_calculated_adjustment_enhanced(gross_amount, words, vendor_name):
    """Apply discount and shipping adjustments to gross amount, return enhanced data."""
    try:
        # Use Decimal for precise calculations to avoid floating-point precision issues
        total_amount = Decimal(gross_amount.replace(',', ''))

        # Get shipping cost
        shipping_cost_str = _extract_shipping_cost(words, vendor_name)
        shipping_cost = Decimal(shipping_cost_str.replace(',', '')) if shipping_cost_str else Decimal('0.0')

        # Get discount terms using standard extraction
        discount_terms = _extract_discount_terms(words, vendor_name).strip()

        # Subtract shipping cost first
        amount_after_shipping = total_amount - shipping_cost

        # Parse discount percentage if present
        discount_percentage = _extract_percentage_from_terms(discount_terms)
        if discount_percentage:
            discount_rate = Decimal(discount_percentage) / Decimal('100.0')
            # Apply discount using Decimal arithmetic
            final_amount = amount_after_shipping * (Decimal('1.0') - discount_rate)

            return _create_result(
                total_amount=format_currency(float(final_amount)),
                calculation_method='calculated',
                discount_type='percentage',
                discount_value=discount_percentage,
                pre_discount_amount=format_currency(float(amount_after_shipping))
            )
        else:
            # No discount found, return amount after shipping
            return _create_result(
                total_amount=format_currency(float(amount_after_shipping)),
                calculation_method='calculated'
            )

    except (ValueError, TypeError):
        # Return original if calculation fails
        return _create_result(gross_amount, 'gross')

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
        return format_currency(result)
    except (ValueError, TypeError):
        return label_result  # Fallback to label result

def _extract_with_label_fallback(words, vendor_name):
    """TIER 2: Try to extract using common total/balance labels."""

    # First, check if this vendor has a specific label defined
    vendor_specific_label = SPECIAL_VENDOR_LABELS.get(vendor_name)
    if vendor_specific_label:

        normalized_words = normalize_words(words, first_page_only=False)

        # For Simms, handle "total amt due" appearing within a sentence
        if vendor_name == "Simms" and vendor_specific_label == "total amt due":
            # Look for the phrase "total amt due" within the combined text
            all_text = " ".join([w.get("text", "") for w in normalized_words]).lower()
            if "total amt due" in all_text:

                # Find the position where "total amt due" appears and look for currency after it
                for i, word in enumerate(normalized_words):
                    word_text = word.get("text", "").lower()
                    # Check if this word and the next few words form "total amt due"
                    combined_text = ""
                    start_word = None
                    for j in range(i, min(i + 5, len(normalized_words))):
                        combined_text += " " + normalized_words[j].get("text", "").lower()
                        if "total amt due" in combined_text.strip():
                            start_word = normalized_words[j]
                            break

                    if start_word:
                        # Look for currency values after this position
                        for k in range(j+1, len(normalized_words)):
                            later_word = normalized_words[k]
                            word_text = later_word.get("text", "")
                            # Handle trailing punctuation that might be attached to currency
                            test_text = word_text.rstrip('.,;!?')  # Remove common trailing punctuation

                            # For Simms, also check for single decimal place currency (e.g., $146.8)
                            is_valid_currency = is_currency(test_text)
                            if not is_valid_currency and vendor_name == "Simms":
                                # Check if it's currency with single decimal place (e.g., $146.8)
                                single_decimal_pattern = r'^\$?\d+\.\d$'
                                if re.match(single_decimal_pattern, test_text):
                                    is_valid_currency = True

                            if is_valid_currency:
                                value = test_text
                                cleaned = clean_currency(preprocess_currency_text(value))
                                try:
                                    amount = float(cleaned)
                                    return format_currency(amount)
                                except Exception:
                                    continue
                        break

        label_positions = find_label_positions(normalized_words, label_type=None, custom_label=vendor_specific_label)


        value = find_value_to_right(normalized_words, label_positions, is_currency, strict=True)
        if value:
            cleaned = clean_currency(preprocess_currency_text(value))
            try:
                amount = float(cleaned)
                return format_currency(amount)
            except Exception:
                pass

    # If no vendor-specific label or it failed, use common fallback labels
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
    
    # Use centralized currency detection
    
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
    return format_currency(best_candidate['amount'])

def preprocess_currency_text(text):
    """Handle specific currency-related CIDs and symbols, including parentheses for negative amounts"""
    # Only handle known currency CIDs
    currency_cid_map = {
        "(cid:36)": "$",  # Dollar sign
        # Add others as needed
    }
    for cid, symbol in currency_cid_map.items():
        text = text.replace(cid, symbol)

    # Handle parentheses format for negative amounts: (238.95) -> -238.95
    if text.startswith('(') and text.endswith(')'):
        # Remove parentheses and add minus sign
        inner_text = text[1:-1].strip()
        if inner_text:  # Make sure there's content inside
            text = f"-{inner_text}"

    return text