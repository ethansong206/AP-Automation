"""
Quantity Extractor for AP Automation System

Extracts total shipped quantity from invoices using approach-based system:
- label_inline: Number embedded in label (e.g., "SUBTOTAL 68 Qty")
- label_right: Label with value to right/below (e.g., "Total Quantity: 25")
- column_sum: Sum quantity column (default fallback)
"""

import re
import csv
import os
from .common_extraction import normalize_words, find_label_positions, find_value_to_right
from .discount_terms import extract_discount_terms
from logging_config import get_logger

logger = get_logger(__name__)


# ============================================================================
# CONFIGURATION: Editable patterns and keywords (add new entries as needed)
# ============================================================================

# Inline label patterns for label_inline approach
# Format: (regex_pattern, description)
INLINE_LABEL_PATTERNS = [
    (r'subtotal\s+(\d+)\s+qty', 'subtotal qty'),      # Altra, Smartwool, TNF
    (r'total\s+items\s+(\d+)', 'total items'),        # Arcade Belts
    (r'net\s+total\s+(\d+)\s+usd', 'net total usd'),  # Patagonia
    (r'totals\s+\d+\s+\d+\s+(\d+)', 'totals'),        # Smith Sport Optics
    (r'quantity:\s+(\d+)\s+total', 'quantity: total'),# Toad & Co
    (r'(\d+)\s+units\s+value', 'units value')         # Gentle Fawn
]

# Labels to try for label_right approach (value to the right of label)
LABEL_RIGHT_PATTERNS = [
    'total quantity shipped',
    'mdse total',
    'qty shipped total',
    'total units shipped',
    'total units shipped:',
    'total units',
    'total quantity',
    'total qty',
    'product totals',
    'total pairs',
    'sum of quantity',
    'quantity total',
    'total:',
    'quantity:',
]

# Labels to try for label_left approach (value to the left of label)
LABEL_LEFT_PATTERNS = [
    'total quantity',
    'total qty',
    'subtotal',
    'total',
]

# Labels to try for label_below approach (value below label)
LABEL_BELOW_PATTERNS = [
    'total units',
    'total quantity',
    'total qty',
]

# Column header patterns for column_sum approach
# Format: strings with space-separated words for multi-word patterns
# Priority order: first match wins
COLUMN_HEADER_PATTERNS = [
    'ordered shipped b.o.',
    'qty shipped',
    'quantity shipped',
    'ship qty',
    'shipped qty',
    'qtyunit',
    'quantity',
    'qty.',
    'shipped',
    'qty invoiced',
    'qty',
    'invoiced',
    'ship-b/o-cancel',
    'b/o ship sku',
]

# Row exclusion keywords for column_sum approach
# Rows containing these keywords will be skipped when summing
ROW_EXCLUSION_KEYWORDS = [
    'freight',
    'days',
    'frt',
    'surcharge',
    'shipping',
    'service',
    'fowhlsl',
    'jay street',
    'park ave',
    'olympic blvd',
    'raleigh, nc',
    'total usd',
    'pro number',
    'h no cost',
    '.nofreight',
    'reship',
    'postage',
    'f ups',
    'f post',
    'to page',
    'f fed ex',
    'discount (general)',
    'definitions',
    'quotes and order',
    'prices and terms',
    'delivery',
    'risk assumption',
    'inspection obligation',
    '518 great',
    'central avenue',
    'competent authority',
    'hook small',
    'impose a surcharge',
    'tfo warranty',
    'can ship asap',
    'secure paddles',
    'demo credit',
    'total quantity',
    'fedex ground',
    'f truck',
]

# ============================================================================


def _load_quantity_approach_map():
    """Load quantity approach mapping from CSV file."""
    approach_map = {}
    csv_path = os.path.join(os.path.dirname(__file__), '..', 'quantity_approach_map.csv')

    if not os.path.exists(csv_path):
        logger.warning(f"Quantity approach map not found: {csv_path}")
        return approach_map

    try:
        with open(csv_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                vendor = row.get('vendor_name', '').strip()
                approach = row.get('approach', '').strip()
                if vendor and approach:
                    approach_map[vendor] = approach
        logger.info(f"Loaded {len(approach_map)} quantity approach mappings")
    except Exception as e:
        logger.error(f"Failed to load quantity approach map: {e}")

    return approach_map


# Load approach map at module level
QUANTITY_APPROACH_MAP = _load_quantity_approach_map()


def is_integer_like(text):
    """
    Check if text looks like a whole number (or whole number with .00).
    Rejects decimal numbers like -261.79 to avoid matching currency amounts.
    """
    text = str(text).strip()
    # Remove commas to handle formatted numbers like "1,767"
    text = text.replace(',', '')
    try:
        value = float(text)
        # Accept only whole numbers or numbers ending in .00
        return value == int(value)
    except (ValueError, TypeError):
        return False


def is_integer_no_decimals(text):
    """
    Check if text is an integer without any decimal point in original text.
    Used by label-based extraction methods to avoid matching currency amounts.
    Rejects values like "1,854.00" even though they represent whole numbers.
    Accepts values like "1854" or "1,854" (no decimal point).
    """
    text = str(text).strip()
    # Reject if there's a decimal point in the original text
    if '.' in text:
        return False
    # Remove commas and check if it's a valid integer
    text = text.replace(',', '')
    try:
        int(text)
        return True
    except (ValueError, TypeError):
        return False


def is_valid_quantity(text):
    """
    Check if text is a valid quantity value for summing.
    Filters out large numbers (prices, ZIP codes, item numbers, etc.)
    that are unlikely to be single-line quantities.

    Returns True only if:
    - Text is integer-like (whole number)
    - Value is <= 999 (single line quantities rarely exceed 3 digits)
    """
    if not is_integer_like(text):
        return False

    try:
        text = str(text).strip().replace(',', '')
        value = abs(float(text))
        # Single line quantities should not exceed 999
        # This filters out: prices (3657), ZIP codes (27607), item numbers, etc.
        return value <= 999
    except (ValueError, TypeError):
        return False


def normalize_quantity(quantity_str):
    """Normalize quantity string to remove unnecessary decimals (e.g., '3.00' -> '3')."""
    try:
        # Remove commas to handle formatted numbers like "1,767"
        clean_str = str(quantity_str).replace(',', '')
        qty_value = float(clean_str)
        # Return as integer string if it's a whole number
        if qty_value == int(qty_value):
            return str(int(qty_value))
        return str(qty_value)
    except (ValueError, TypeError):
        return quantity_str


def _extract_label_inline(words, vendor_name):
    """
    Extract quantity from inline label patterns where number appears within label text.
    Examples:
    - "SUBTOTAL 68 Qty" → 68
    - "Total Items 181" → 181
    """
    all_text = ' '.join([w.get('text', '') for w in words]).lower()

    for pattern, label_name in INLINE_LABEL_PATTERNS:
        match = re.search(pattern, all_text)
        if match:
            quantity = match.group(1)
            quantity = normalize_quantity(quantity)
            logger.debug(f"{vendor_name}: Found inline label '{label_name}' = {quantity}")
            return quantity

    return None


def _extract_label_right(words, vendor_name, preferred_label=None):
    """
    Extract quantity from label with value to the right (uses spatial coordinates).
    Example: "Total Quantity Shipped" with "1" to the right
    Only searches on the same page as the label.

    Args:
        words: List of word dictionaries from PDF
        vendor_name: Name of vendor
        preferred_label: Optional specific label to search for (overrides LABEL_RIGHT_PATTERNS)
    """
    normalized_words = normalize_words(words, first_page_only=False)

    # Use preferred label if provided, otherwise use all patterns
    labels_to_search = [preferred_label] if preferred_label else LABEL_RIGHT_PATTERNS

    for label in labels_to_search:
        label_positions = find_label_positions(normalized_words, label_type=None, custom_label=label)

        for label_x0, label_x1, label_y, label_bottom in label_positions:
            # Get all matching pages for this label position
            matching_pages = []
            for word in normalized_words:
                if (abs(word['x0'] - label_x0) < 1 and
                    abs(word['top'] - label_y) < 1):
                    page = word.get('page_num', 0)
                    if page not in matching_pages:
                        matching_pages.append(page)

            if not matching_pages:
                matching_pages = [0]  # Default to first page if not found

            # Check last page first (if multiple pages), then first page
            # This handles invoices where total appears on all pages but value only on last
            max_page = max(w.get('page_num', 0) for w in normalized_words)
            pages_to_check = []
            if max_page in matching_pages and max_page > 0:
                pages_to_check.append(max_page)
            if 0 in matching_pages and 0 not in pages_to_check:
                pages_to_check.append(0)

            # If no last or first page match, just use first matching page
            if not pages_to_check:
                pages_to_check = matching_pages[:1]

            for label_page in pages_to_check:
                # Look for values to the RIGHT of the label on this page
                candidates = [
                    w for w in normalized_words
                    if w.get('page_num', 0) == label_page  # Same page as label
                    and w['x0'] > label_x1  # Word starts after label ends
                    and abs(w['top'] - label_y) <= 20  # Same horizontal line
                    and (is_integer_like(w['orig']) if 'columbia river' in vendor_name.lower() or 'johnnie-o' in vendor_name.lower()
                         else is_integer_no_decimals(w['orig']))
                ]

                if candidates:
                    # Get the closest one to the right (leftmost of right candidates)
                    closest = min(candidates, key=lambda w: w['x0'])
                    value = normalize_quantity(closest['orig'].strip())
                    logger.debug(f"{vendor_name}: Found label_right '{label}' = {value} on page {label_page}")
                    return value

    return None


def _extract_label_left(words, vendor_name):
    """
    Extract quantity from label with value to the left (uses spatial coordinates).
    Example: "28" with "Total Quantity" to the right of it
    Only searches on the same page as the label.
    """
    normalized_words = normalize_words(words, first_page_only=False)

    for label in LABEL_LEFT_PATTERNS:
        label_positions = find_label_positions(normalized_words, label_type=None, custom_label=label)

        for label_x0, label_x1, label_y, label_bottom in label_positions:
            # Get the page number for this label
            label_page = None
            for word in normalized_words:
                if (abs(word['x0'] - label_x0) < 1 and
                    abs(word['top'] - label_y) < 1):
                    label_page = word.get('page_num', 0)
                    break

            if label_page is None:
                label_page = 0  # Default to first page if not found

            # Look for values to the LEFT of the label on the same page
            candidates = [
                w for w in normalized_words
                if w.get('page_num', 0) == label_page  # Same page as label
                and w['x1'] < label_x0  # Word ends before label starts
                and abs(w['top'] - label_y) <= 5  # Same horizontal line
                and is_integer_no_decimals(w['orig'])
            ]

            if candidates:
                # Get the closest one to the left (rightmost of left candidates)
                closest = max(candidates, key=lambda w: w['x1'])
                value = normalize_quantity(closest['orig'].strip())
                logger.debug(f"{vendor_name}: Found label_left '{label}' = {value} on page {label_page}")
                return value

    return None


def _extract_label_below(words, vendor_name):
    """
    Extract quantity from label with value below (uses spatial coordinates).
    Example: "Total Quantity" with "25" on the line below
    Only searches on the same page as the label.
    """
    normalized_words = normalize_words(words, first_page_only=False)

    for label in LABEL_BELOW_PATTERNS:
        label_positions = find_label_positions(normalized_words, label_type=None, custom_label=label)

        for label_x0, label_x1, label_y, label_bottom in label_positions:
            label_mid_x = (label_x0 + label_x1) / 2

            # Get the page number for this label
            label_page = None
            for word in normalized_words:
                if (abs(word['x0'] - label_x0) < 1 and
                    abs(word['top'] - label_y) < 1):
                    label_page = word.get('page_num', 0)
                    break

            if label_page is None:
                label_page = 0  # Default to first page if not found

            candidates = []
            for word in normalized_words:
                # Only consider words on the same page as the label
                if word.get('page_num', 0) != label_page:
                    continue

                word_mid_x = (word['x0'] + word['x1']) / 2
                vertical_distance = word['top'] - label_y

                # Check if below and horizontally aligned
                if (0 < vertical_distance <= 100 and
                    abs(word_mid_x - label_mid_x) <= 45 and
                    is_integer_no_decimals(word['orig'])):
                    candidates.append((word, vertical_distance))

            if candidates:
                # Return closest one below
                closest = min(candidates, key=lambda x: x[1])
                value = normalize_quantity(closest[0]['orig'].strip())
                logger.debug(f"{vendor_name}: Found label_below '{label}' = {value} on page {label_page}")
                return value

    return None


def _group_words_into_rows(words, y_tolerance=10):
    """Group words into rows based on Y-coordinate."""
    if not words:
        return []

    sorted_words = sorted(words, key=lambda w: (w.get('page_num', 0), w.get('top', 0)))

    rows = []
    current_row = [sorted_words[0]]
    current_y = sorted_words[0].get('top', 0)
    current_page = sorted_words[0].get('page_num', 0)

    for word in sorted_words[1:]:
        word_y = word.get('top', 0)
        word_page = word.get('page_num', 0)

        if abs(word_y - current_y) > y_tolerance or word_page != current_page:
            rows.append(current_row)
            current_row = [word]
            current_y = word_y
            current_page = word_page
        else:
            current_row.append(word)

    if current_row:
        rows.append(current_row)

    return rows


def _extract_column_sum(words, vendor_name, preferred_label=None):
    """
    Sum quantity column values (default fallback approach).
    Finds column header by searching for multi-word patterns, then sums values below.

    To add new header patterns, add them to COLUMN_HEADER_PATTERNS at top of file.
    To add new row exclusions, add keywords to ROW_EXCLUSION_KEYWORDS at top of file.

    Args:
        words: List of word dictionaries from PDF
        vendor_name: Name of vendor
        preferred_label: Optional specific label to search for (overrides COLUMN_HEADER_PATTERNS)
    """
    # Get first page words
    first_page_words = [w for w in words if w.get('page_num', 0) == 0]

    if not first_page_words:
        logger.debug(f"{vendor_name}: No words on first page")
        return None

    # Search for quantity column header using all defined patterns
    header_x_range = None
    header_y = None

    # Use preferred label if provided, otherwise use all patterns
    patterns_to_search = [preferred_label] if preferred_label else COLUMN_HEADER_PATTERNS

    for pattern in patterns_to_search:
        # Split pattern into words for matching
        pattern_words = pattern.split()
        pattern_length = len(pattern_words)

        # Slide through words looking for this pattern
        for i in range(len(first_page_words) - pattern_length + 1):
            # Check if consecutive words match the pattern
            matches = True
            matched_words = []

            for j, pattern_word in enumerate(pattern_words):
                word = first_page_words[i + j]
                if word.get('text', '').lower() != pattern_word:
                    matches = False
                    break
                matched_words.append(word)

            if matches:
                # Verify all words are on the same line (within 5px Y tolerance)
                first_y = matched_words[0].get('top', 0)
                if all(abs(w.get('top', 0) - first_y) < 5 for w in matched_words):
                    # Found matching pattern
                    header_x_range = (matched_words[0]['x0'], matched_words[-1]['x1'])
                    header_y = first_y
                    logger.debug(f"{vendor_name}: Found '{pattern.title()}' column at x={header_x_range[0]:.1f}-{header_x_range[1]:.1f}, y={header_y:.1f}")
                    break

        if header_x_range:
            break

    if not header_x_range:
        logger.debug(f"{vendor_name}: No quantity column header found")
        return None

    # Calculate column midpoint and tolerance for summing
    header_x_mid = (header_x_range[0] + header_x_range[1]) / 2

    # Column tolerance - vendor-specific adjustments
    column_tolerance = 40  # Default tolerance to capture values slightly offset from header
    if 'icemule' in vendor_name.lower():
        column_tolerance = 20  # IceMule: Tighter tolerance to exclude backordered items section
    if 'salomon' in vendor_name.lower():
        column_tolerance = 20  # Salomon: Tighter tolerance to exclude size breakdown numbers on the left
    if 'simms' in vendor_name.lower():
        column_tolerance = 20  # Simms: Tighter tolerance to exclude backordered items column
    if 'temple fork' in vendor_name.lower():
        column_tolerance = 20  # Temple Fork Outfitters: Tighter tolerance to exclude item descriptions
    if 'topo athletic' in vendor_name.lower():
        column_tolerance = 20  # Topo Athletic: Columns are really close together

    # Build a map of page -> header_y for each page that has the header
    # This allows us to handle repeated headers on multi-page invoices
    page_headers = {0: header_y}  # Page 0 always has the header we found

    # Check subsequent pages for repeated headers at similar X position
    max_page = max(w.get('page_num', 0) for w in words) if words else 0
    for page_num in range(1, max_page + 1):
        page_words = [w for w in words if w.get('page_num', 0) == page_num]
        if not page_words:
            continue

        # Look for header pattern on this page
        for pattern in COLUMN_HEADER_PATTERNS:
            pattern_words_list = pattern.split()
            pattern_length = len(pattern_words_list)

            for i in range(len(page_words) - pattern_length + 1):
                matches = True
                matched_words = []

                for j, pattern_word in enumerate(pattern_words_list):
                    word = page_words[i + j]
                    if word.get('text', '').lower() != pattern_word:
                        matches = False
                        break
                    matched_words.append(word)

                if matches:
                    first_y = matched_words[0].get('top', 0)
                    if all(abs(w.get('top', 0) - first_y) < 5 for w in matched_words):
                        # Found header on this page - check if X position is similar
                        page_header_x = (matched_words[0]['x0'] + matched_words[-1]['x1']) / 2
                        if abs(page_header_x - header_x_mid) <= column_tolerance:
                            page_headers[page_num] = first_y
                            logger.debug(f"{vendor_name}: Found repeated header on page {page_num} at y={first_y:.1f}")
                            break

            if page_num in page_headers:
                break

    # Sum all numeric values in the column, respecting page-specific header positions
    # Also track Y-position to stop at large gaps (footer/address sections)
    # When multiple values are within tolerance on the same row, pick the closest to header midpoint
    total_quantity = 0
    found_any_values = False  # Track if we found any integer-like values in the column
    last_y_per_page = {}  # Track last Y position for each page

    # Maximum vertical gap to continue summing (vendor-specific adjustments)
    max_gap = 106
    if 'backpacker\'s pantry' in vendor_name.lower():
        max_gap = 1000  # Backpacker's Pantry has large gaps between each line item
    if 'dapper ink' in vendor_name.lower():
        max_gap = 1000  # Dapper Ink has large gaps between each item line
    if 'hobie' in vendor_name.lower():
        max_gap = 150   # Hobie has larger gaps between header and first data row on multi-page invoices
    if 'industrial revolution' in vendor_name.lower():
        max_gap = 150   # Industrial Revolution has similar multi-page layout with larger gaps
    if 'liberty mountain' in vendor_name.lower():
        max_gap = 1000  # Liberty Mountain has empty spaces when item backordered
    if 'simms' in vendor_name.lower():
        max_gap = 1000  # Simms has empty spaces when item backordered
    if 'topo athletic' in vendor_name.lower():
        max_gap = 150   # Topo Athletic has large gaps between lines

    y_tolerance_for_row = 8  # Pixels to consider values on the same row

    # Vendor-specific row tolerance adjustments
    if 'topo athletic' in vendor_name.lower():
        y_tolerance_for_row = 3  # TOPO ATHLETIC has tightly spaced rows that shouldn't be grouped

    # Group all integer-like values by row (page, y-coordinate)
    # This allows us to handle multiple columns and pick the closest value per row
    rows_with_candidates = {}  # Key: (page, y_rounded), Value: list of (word, distance_to_header)

    for word in words:
        word_y = word.get('top', 0)
        word_x_mid = (word['x0'] + word['x1']) / 2
        word_page = word.get('page_num', 0)

        # Check if word is in the correct column (within tolerance)
        if abs(word_x_mid - header_x_mid) <= column_tolerance:
            # If this page has a header, only include values below it
            if word_page in page_headers:
                if word_y <= page_headers[word_page]:
                    continue  # Skip - above or at header

            word_text = word['text']

            # Salomon-specific: Strip "PR" suffix from quantity values
            if 'salomon' in vendor_name.lower() and word_text.upper().endswith('PR'):
                word_text = word_text[:-2].strip()

            if is_valid_quantity(word_text):
                found_any_values = True
                # Calculate distance from header midpoint
                distance = abs(word_x_mid - header_x_mid)

                # Round Y coordinate to group rows (within y_tolerance_for_row pixels)
                y_rounded = round(word_y / y_tolerance_for_row) * y_tolerance_for_row
                row_key = (word_page, y_rounded)

                if row_key not in rows_with_candidates:
                    rows_with_candidates[row_key] = []
                rows_with_candidates[row_key].append((word, distance))

    # Establish reference column X position from rows with multiple candidates
    # This helps us identify the correct column when some rows have missing values
    reference_column_x = None
    multi_candidate_rows = [row_key for row_key, candidates in rows_with_candidates.items() if len(candidates) > 1]

    if multi_candidate_rows:
        # Calculate average X position of closest candidates from multi-candidate rows
        closest_x_positions = []
        for row_key in multi_candidate_rows:
            candidates = rows_with_candidates[row_key]
            closest_word, closest_distance = min(candidates, key=lambda x: x[1])
            closest_x_positions.append((closest_word['x0'] + closest_word['x1']) / 2)

        if closest_x_positions:
            reference_column_x = sum(closest_x_positions) / len(closest_x_positions)
            logger.debug(f"{vendor_name}: Established reference column at x={reference_column_x:.1f} from {len(closest_x_positions)} multi-candidate rows")

    # Now process each row, selecting only the closest value to the header midpoint
    # Sort by page and Y position for sequential processing
    sorted_rows = sorted(rows_with_candidates.keys(), key=lambda k: (k[0], k[1]))
    reference_tolerance = 20  # Pixels - how close a single candidate must be to reference column

    for row_key in sorted_rows:
        word_page, word_y = row_key
        candidates = rows_with_candidates[row_key]

        # Check vertical gap from last value on this page
        if word_page in last_y_per_page:
            gap = word_y - last_y_per_page[word_page]
            if gap > max_gap:
                logger.debug(f"{vendor_name}: Stopping sum on page {word_page} - gap of {gap:.1f}px exceeds {max_gap}px")
                continue  # Stop summing on this page - hit footer/address section
        elif word_page in page_headers and word_page > 0:
            # First value on a NON-FIRST page that has a header - check gap from header
            # Skip this check for page 0 since the header is at the top and may have large gap to first data row
            gap_from_header = word_y - page_headers[word_page]
            if gap_from_header > max_gap:
                logger.debug(f"{vendor_name}: Stopping sum on page {word_page} - first value gap of {gap_from_header:.1f}px from header exceeds {max_gap}px")
                continue  # First value is too far from header
        elif word_page > 0 and word_page not in page_headers:
            # New page without header - continue processing, respecting max_gap
            # The gap check will stop us if we hit a footer/address section
            if reference_column_x is not None:
                logger.debug(f"{vendor_name}: Page {word_page} has no header, but continuing with reference column at x={reference_column_x:.1f}")
            else:
                logger.debug(f"{vendor_name}: Page {word_page} has no header and no reference column, continuing with gap-based validation")

        # Select the candidate closest to the header midpoint
        closest_word, closest_distance = min(candidates, key=lambda x: x[1])

        # If we have a reference column and this row has only one candidate,
        # verify it's actually from the reference column (not a stray value from another column)
        if reference_column_x is not None and len(candidates) == 1:
            candidate_x = (closest_word['x0'] + closest_word['x1']) / 2
            distance_from_reference = abs(candidate_x - reference_column_x)

            if distance_from_reference > reference_tolerance:
                logger.debug(f"{vendor_name}: Skipping single candidate {closest_word['text']} at x={candidate_x:.1f} - {distance_from_reference:.1f}px from reference column (likely wrong column)")
                continue

        try:
            qty_text = closest_word['text']

            # Salomon-specific: Strip "PR" suffix from quantity values
            if 'salomon' in vendor_name.lower() and qty_text.upper().endswith('PR'):
                qty_text = qty_text[:-2].strip()

            qty = float(qty_text)

            # Check if this row should be skipped (use actual Y from closest_word, not rounded)
            actual_y = closest_word.get('top', 0)
            row_words = [w for w in words
                         if w.get('page_num', 0) == word_page
                         and abs(w.get('top', 0) - actual_y) <= y_tolerance_for_row]
            row_text = ' '.join([w.get('text', '') for w in row_words]).lower()

            # Skip row if it contains any exclusion keyword
            skip_row = any(keyword in row_text for keyword in ROW_EXCLUSION_KEYWORDS)

            # Vendor-specific exclusions
            if 'icemule' in vendor_name.lower() and 'yes' in row_text:
                skip_row = True

            # Oboz: Exclude rows containing "size" or "quantity" (breakdown rows)
            if 'oboz' in vendor_name.lower():
                if 'size' in row_text or 'quantity' in row_text:
                    skip_row = True

            if skip_row:
                logger.debug(f"{vendor_name}: Skipping excluded row with value {qty}")
                continue

            total_quantity += qty
            last_y_per_page[word_page] = word_y  # Update last Y for this page

            if len(candidates) > 1:
                logger.debug(f"{vendor_name}: Selected closest value {qty} (distance={closest_distance:.1f}px) from {len(candidates)} candidates on page {word_page}, y={word_y:.1f}. Total now: {total_quantity}")
            else:
                logger.debug(f"{vendor_name}: Added {qty} from page {word_page}, y={word_y:.1f}. Total now: {total_quantity}")
        except (ValueError, TypeError):
            continue

    if 'blundstone' in vendor_name.lower():
        return str(int(total_quantity/2))
    if 'oregon freeze dry' in vendor_name.lower():
        return str(int(total_quantity/2))

    # If we found any values in the column, return the sum (even if 0)
    # If we found no values at all, return None
    if found_any_values:
        # Return as integer if whole number
        if total_quantity == int(total_quantity):
            return str(int(total_quantity))
        return str(total_quantity)

    return None


def extract_quantity(words, vendor_name):
    """
    Main quantity extraction function.
    Uses approach map for known vendors, falls back to column_sum for unknown vendors.

    Returns:
        tuple: (quantity_value, metadata_dict) where metadata contains:
            - 'approach_used': The approach that successfully extracted the value
            - 'is_fallback': Boolean indicating if a fallback approach was used
            - 'configured_approaches': List of approaches that were configured
    """
    logger.debug(f"Extracting quantity for vendor: {vendor_name}")

    # Get approach(es) from map
    approach_str = QUANTITY_APPROACH_MAP.get(vendor_name, '')
    approaches = [a.strip() for a in approach_str.split(',') if a.strip()] if approach_str else []

    # If no approaches defined, use column_sum as default
    if not approaches:
        approaches = ['column_sum']

    # Approach function mapping
    approach_functions = {
        'label_inline': _extract_label_inline,
        'label_right': _extract_label_right,
        'label_left': _extract_label_left,
        'label_below': _extract_label_below,
        'column_sum': _extract_column_sum,
    }

    # Try each approach in order
    quantity = None
    approach_used = None
    approach_index = -1

    for idx, approach in enumerate(approaches):
        # Check if approach has a colon (e.g., "column_sum:qty")
        preferred_label = None
        if ':' in approach:
            approach, preferred_label = approach.split(':', 1)
            approach = approach.strip()
            preferred_label = preferred_label.strip()

        func = approach_functions.get(approach)
        if func:
            # Pass preferred_label to column_sum and label_right
            if (approach == 'column_sum' or approach == 'label_right') and preferred_label:
                quantity = func(words, vendor_name, preferred_label=preferred_label)
            else:
                quantity = func(words, vendor_name)
            if quantity:
                logger.debug(f"{vendor_name}: Approach '{approach}' succeeded with value: {quantity}")
                approach_used = approach
                approach_index = idx
                break
        else:
            logger.warning(f"{vendor_name}: Unknown approach '{approach}'")

    # If no quantity found and column_sum wasn't already tried, use it as fallback
    if not quantity and 'column_sum' not in approaches:
        logger.debug(f"{vendor_name}: No quantity found with configured approaches: {approaches}. Trying column_sum as fallback.")
        quantity = _extract_column_sum(words, vendor_name)
        if quantity:
            approach_used = 'column_sum'
            approach_index = len(approaches)  # Indicates it was a fallback
            logger.debug(f"{vendor_name}: Fallback column_sum succeeded with value: {quantity}")

    if not quantity:
        logger.debug(f"{vendor_name}: No quantity found with approaches: {approaches}")
        metadata = {
            'approach_used': None,
            'is_fallback': False,
            'configured_approaches': approaches
        }
        return '', metadata

    # Apply credit memo logic (negate for credit documents)
    discount_terms = extract_discount_terms(words, vendor_name)
    is_credit = discount_terms and any(term in discount_terms.upper()
                                       for term in ['CREDIT MEMO', 'CREDIT NOTE'])

    if is_credit:
        try:
            qty_value = float(quantity)
            if qty_value > 0:
                qty_value = -qty_value
            quantity = str(int(qty_value)) if qty_value == int(qty_value) else str(qty_value)
            logger.debug(f"{vendor_name}: Negated quantity for credit document: {quantity}")
        except (ValueError, TypeError):
            pass

    # Build metadata
    metadata = {
        'approach_used': approach_used,
        'is_fallback': approach_index > 0,  # True if not the first approach
        'configured_approaches': approaches
    }

    return quantity, metadata
