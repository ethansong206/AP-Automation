import re
from .common_extraction import (
    normalize_words,
    find_label_positions,
    find_value_to_right,
    find_value_below,
    search_for_pattern
)
from logging_config import get_logger

logger = get_logger(__name__)

def extract_invoice_number(words, vendor_name):
    """
    Extract invoice number from document
    """
    normalized_words = normalize_words(words)
    
    # Find invoice label positions
    label_positions = find_label_positions(normalized_words, label_type="invoice")
    
    # Arc'teryx-specific logic: check discount terms to determine label type
    if vendor_name == "Arc'teryx":
        from .discount_terms import extract_discount_terms
        discount_terms = extract_discount_terms(words, vendor_name)
        
        if discount_terms == "CREDIT NOTE":
            # For credit notes, look specifically under "Credit Note" labels only
            credit_note_positions = []
            for i in range(len(normalized_words) - 1):
                first = normalized_words[i]
                second = normalized_words[i + 1]
                if first["text"] == "credit" and second["text"] == "note":
                    credit_note_positions.append((first["x0"], second["x1"], first["top"]))
            
            # Look below credit note labels specifically
            if credit_note_positions:
                arc_result = find_value_below(
                    normalized_words, 
                    credit_note_positions,
                    lambda text: is_potential_invoice_number(text, vendor_name) and len(text.strip()) >= 10,
                    max_distance=150
                )
                if arc_result:
                    return arc_result
        else:
            # For regular invoices, look below invoice labels
            arc_result = find_value_below(
                normalized_words, 
                label_positions,
                lambda text: is_potential_invoice_number(text, vendor_name) and len(text.strip()) >= 10,
                max_distance=150
            )
            if arc_result:
                return arc_result
    
    # Vendor-specific: Add "number" as a label for Oboz
    if vendor_name == "Oboz Footwear LLC":
        for idx, w in enumerate(normalized_words):
            if w["text"] == "number":
                label_positions.append((w["x0"], w["x1"], w["top"]))
    
    # Darn Tough-specific logic: use only "Invoice ID" labels instead of "Invoice"
    if vendor_name == "Darn Tough":
        # Clear existing invoice labels and use only "Invoice ID" labels
        invoice_id_positions = []
        for i in range(len(normalized_words) - 1):
            first = normalized_words[i]
            second = normalized_words[i + 1]
            if first["text"] == "invoice" and second["text"] == "id":
                invoice_id_positions.append((first["x0"], second["x1"], second["top"]))
        
        # If we found Invoice ID labels, use them exclusively
        if invoice_id_positions:
            # Try below first (likely location for Darn Tough)
            darn_tough_result = find_value_below(
                normalized_words, 
                invoice_id_positions,
                lambda text: is_potential_invoice_number(text, vendor_name),
                max_distance=150
            )
            if darn_tough_result:
                return darn_tough_result
            
            # Try right strict as fallback
            darn_tough_result = find_value_to_right(
                normalized_words, 
                invoice_id_positions,
                lambda text: is_potential_invoice_number(text, vendor_name),
                strict=True
            )
            if darn_tough_result:
                return darn_tough_result
            
            # Try right loose as last resort
            darn_tough_result = find_value_to_right(
                normalized_words, 
                invoice_id_positions,
                lambda text: is_potential_invoice_number(text, vendor_name),
                strict=False
            )
            if darn_tough_result:
                return darn_tough_result
        
        # If no Invoice ID labels found or no results, return empty to avoid date confusion
        return ""
    
    # Helinox-specific logic: look for "Invoice #" pattern specifically to avoid "Invoice Date"
    if vendor_name == "Helinox":
        helinox_positions = []
        # Use original words since # gets stripped in normalization
        for i in range(len(words) - 1):
            first = words[i]
            second = words[i + 1]
            if first["text"].lower().strip() == "invoice" and second["text"].strip() == "#":
                helinox_positions.append((first["x0"], second["x1"], first["top"]))
        
        # If we found "Invoice #" labels, use them exclusively
        if helinox_positions:
            helinox_result = find_value_to_right(
                normalized_words, 
                helinox_positions,
                lambda text: is_potential_invoice_number(text, vendor_name),
                strict=True
            )
            if helinox_result:
                return helinox_result
            
            # Try looser search if strict didn't work
            helinox_result = find_value_to_right(
                normalized_words, 
                helinox_positions,
                lambda text: is_potential_invoice_number(text, vendor_name),
                strict=False
            )
            if helinox_result:
                return helinox_result
        
        # If no Invoice # labels found or no results, return empty to avoid date confusion
        return ""
    
    # Hydro Flask-specific logic: look for "INVOICE NO" pattern and search below to avoid phone numbers
    if vendor_name == "Hydro Flask":
        hydro_flask_positions = []
        # Look for "INVOICE" followed by "NO" pattern
        for i in range(len(normalized_words) - 1):
            first = normalized_words[i]
            second = normalized_words[i + 1]
            if first["text"] == "invoice" and second["text"] == "no":
                hydro_flask_positions.append((first["x0"], second["x1"], first["top"]))
        
        # If we found "INVOICE NO" labels, search below them
        if hydro_flask_positions:
            hydro_flask_result = find_value_below(
                normalized_words, 
                hydro_flask_positions,
                lambda text: is_potential_invoice_number(text, vendor_name),
                max_distance=150
            )
            if hydro_flask_result:
                return hydro_flask_result
        
        # If no INVOICE NO labels found or no results, return empty to avoid phone confusion
        return ""
    
    # Eagles Nest Outfitters-specific logic: check discount terms for credit memos
    if vendor_name == "Eagles Nest Outfitters, Inc.":
        from .discount_terms import extract_discount_terms
        discount_terms = extract_discount_terms(words, vendor_name)
        
        if discount_terms == "CREDIT MEMO":
            # For credit memos, look for "Credit #" labels specifically
            credit_positions = []
            for i in range(len(normalized_words) - 1):
                first = normalized_words[i]
                second = normalized_words[i + 1]
                if first["text"] == "credit" and (second["text"] == "#" or (second["text"] == "" and second["orig"] == "#")):
                    credit_positions.append((first["x0"], second["x1"], first["top"]))
            
            # If we found "Credit #" labels, search to the right
            if credit_positions:
                credit_result = find_value_to_right(
                    normalized_words, 
                    credit_positions,
                    lambda text: is_potential_invoice_number(text, vendor_name),
                    strict=True
                )
                if credit_result:
                    return credit_result
    
    # Nite Ize Inc-specific logic: look for "Transaction Number" first, then "Order Number"
    if vendor_name == "Nite Ize Inc":
        # First, look for "Transaction Number" labels
        transaction_positions = []
        for i in range(len(normalized_words) - 1):
            first = normalized_words[i]
            second = normalized_words[i + 1]
            if first["text"] == "transaction" and second["text"] == "number":
                transaction_positions.append((first["x0"], second["x1"], first["top"]))
        
        # If we found "Transaction Number" labels, search to the right
        if transaction_positions:
            transaction_result = find_value_to_right(
                normalized_words, 
                transaction_positions,
                lambda text: is_potential_invoice_number(text, vendor_name),
                strict=True
            )
            if transaction_result:
                return transaction_result
        
        # Fallback: look for "Order Number" labels if Transaction Number not found
        order_positions = []
        for i in range(len(normalized_words) - 1):
            first = normalized_words[i]
            second = normalized_words[i + 1]
            if first["text"] == "order" and second["text"] == "number":
                order_positions.append((first["x0"], second["x1"], first["top"]))
        
        # If we found "Order Number" labels, search to the right
        if order_positions:
            order_result = find_value_to_right(
                normalized_words, 
                order_positions,
                lambda text: is_potential_invoice_number(text, vendor_name),
                strict=True
            )
            if order_result:
                return order_result
    
    # Salomon-specific logic: look for "Invoice No." labels and search below
    if vendor_name == "Salomon":
        # Look for "Invoice No." label specifically
        salomon_positions = []
        for i in range(len(normalized_words) - 1):
            first = normalized_words[i]
            second = normalized_words[i + 1]
            if first["text"] == "invoice" and second["text"].startswith("no"):
                salomon_positions.append((first["x0"], second["x1"], first["top"]))
        
        # If we found "Invoice No." labels, search below them for 5+ digit strings
        if salomon_positions:
            def is_valid_salomon_number(text):
                import re
                # Accept any string of 5+ digits
                return re.match(r'^\d{5,}$', text.strip()) is not None
            
            salomon_result = find_value_below(
                normalized_words,
                salomon_positions,
                is_valid_salomon_number,
                max_distance=150
            )
            if salomon_result:
                return salomon_result
    
    # Sea to Summit-specific logic: look for "Invoice No." labels and search to the right
    if vendor_name == "Sea to Summit":
        # Look for "Invoice No." label specifically
        sea_to_summit_positions = []
        for i in range(len(normalized_words) - 1):
            first = normalized_words[i]
            second = normalized_words[i + 1]
            if first["text"] == "invoice" and second["text"].startswith("no"):
                sea_to_summit_positions.append((first["x0"], second["x1"], first["top"]))
        
        # If we found "Invoice No." labels, search to the right
        if sea_to_summit_positions:
            sea_to_summit_result = find_value_to_right(
                normalized_words,
                sea_to_summit_positions,
                lambda text: is_potential_invoice_number(text, vendor_name),
                strict=True
            )
            if sea_to_summit_result:
                return sea_to_summit_result
    
    # Turtlebox Audio LLC-specific logic: first label vertically, check right then below, combine if different
    if vendor_name == "Turtlebox Audio LLC":
        # Find invoice label positions and get the first one vertically (highest on page)
        turtlebox_positions = find_label_positions(normalized_words, "invoice")
        
        if turtlebox_positions:
            # Sort by vertical position (top coordinate) to get first label on page
            first_label = min(turtlebox_positions, key=lambda pos: pos[2])  # pos[2] is top coordinate
            label_x0, label_x1, label_y = first_label
            
            # Check directly to the right
            right_value = find_value_to_right(
                normalized_words,
                [first_label],
                lambda text: len(text.strip()) > 0,  # Accept any non-empty text
                strict=True
            )
            
            # Check directly below
            below_value = find_value_below(
                normalized_words,
                [first_label], 
                lambda text: len(text.strip()) > 0,  # Accept any non-empty text
                max_distance=50
            )
            
            # If both exist and are different, combine them
            if right_value and below_value and right_value != below_value:
                combined = f"{right_value}{below_value}"
                return combined
            # Otherwise return whichever one exists
            elif right_value:
                return right_value
            elif below_value:
                return below_value
    
    # Fishpond-specific logic: for email format, skip first invoice label and use second one
    if vendor_name == "Fishpond":
        from .email_detection import is_email_format
        
        if is_email_format(words):
            # Find all invoice label positions
            fishpond_positions = find_label_positions(normalized_words, "invoice")
            
            # If we have at least 2 labels, skip the first and use the second
            if len(fishpond_positions) >= 2:
                second_label = fishpond_positions[1]  # Use second label (index 1)
                
                # Try to find value to the right of the second label
                fishpond_result = find_value_to_right(
                    normalized_words,
                    [second_label],
                    lambda text: is_potential_invoice_number(text, vendor_name),
                    strict=True
                )
                if fishpond_result:
                    return fishpond_result

    # Add credit memo/note labels
    for i in range(len(normalized_words) - 1):
        first = normalized_words[i]
        second = normalized_words[i + 1]
        if (first["text"] == "credit" and second["text"] in ["memo", "note"]):
            # Combine their bounding boxes for the label position
            label_positions.append((first["x0"], second["x1"], first["top"]))
    
    # Prana-specific logic: check under the label "Reference"
    if vendor_name == "Prana Living LLC":
        logger.debug("Checking for all 'reference' labels for Prana Living LLC")
        for idx, w in enumerate(normalized_words):
            if w["text"] == "reference":
                logger.debug(f"Reference label at index={idx}, x0={w['x0']}, x1={w['x1']}, top={w['top']}, bottom={w['bottom']}")
                # Allow vertical overlap or small positive distance
                candidates = [
                    cand for cand in normalized_words
                    if (cand["x0"] >= w["x0"] - 100 and cand["x1"] <= w["x1"] + 100) and
                       -5 <= (cand["top"] - w["bottom"]) <= 300 and
                       is_potential_invoice_number(cand["text"], vendor_name)
                ]
                logger.debug(f"Candidates found below 'reference': {[c['orig'] for c in candidates]}")
                if candidates:
                    best = sorted(candidates, key=lambda x: abs(x["top"] - w["bottom"]))[0]
                    logger.debug(f"Invoice Number (below 'Reference' for Prana): {best['orig']}")
                    return best["orig"].lstrip("#:").strip()
                #else:
                    logger.debug("No valid invoice number found below this 'reference' label.")
    
    # Prism Designs-specific logic: look for "Invoice" label and check directly below it
    if vendor_name == "Prism Designs":
        logger.debug("Checking for 'Invoice' label for Prism Designs")
        for idx, w in enumerate(normalized_words):
            if w["text"] == "invoice":
                #print(f"[DEBUG] Found 'invoice' label at index={idx}, x0={w['x0']}, x1={w['x1']}, top={w['top']}, bottom={w['bottom']}")
                # Look for values directly below this label with relaxed horizontal alignment
                candidates = [
                    cand for cand in normalized_words
                    if (cand["x0"] >= w["x0"] - 50 and cand["x1"] <= w["x1"] + 100) and
                       5 <= (cand["top"] - w["bottom"]) <= 100 and
                       is_potential_invoice_number(cand["text"], vendor_name)
                ]
                #print(f"[DEBUG] Candidates found below 'invoice': {[c['orig'] for c in candidates]}")
                if candidates:
                    best = sorted(candidates, key=lambda x: abs(x["top"] - w["bottom"]))[0]
                    #print(f"[DEBUG] Invoice Number (below 'Invoice' for Prism Designs): {best['orig']}")
                    return best["orig"].lstrip("#:").strip()
    
    # Nite Ize Inc-specific logic: look for "Order Number" label
    if vendor_name == "Nite Ize Inc":
        #print("[DEBUG] Checking for 'Order Number' label for Nite Ize Inc")
        for idx, w in enumerate(normalized_words):
            # Look for "order" word followed by "number" word
            if w["text"] == "order" and idx < len(normalized_words) - 1 and normalized_words[idx + 1]["text"] == "number":
                order_label = w
                number_label = normalized_words[idx + 1]
                #print(f"[DEBUG] Found 'Order Number' at index={idx}, x0={order_label['x0']}, x1={number_label['x1']}")
                
                # Look for values to the right of this label
                candidates = [
                    cand for cand in normalized_words
                    if (cand["x0"] > number_label["x1"]) and
                       abs(cand["top"] - order_label["top"]) < 20 and
                       is_potential_invoice_number(cand["text"], vendor_name)
                ]
                
                #print(f"[DEBUG] Candidates found next to 'Order Number': {[c['orig'] for c in candidates]}")
                if candidates:
                    # Get the closest candidate to the right
                    best = sorted(candidates, key=lambda x: x["x0"] - number_label["x1"])[0]
                    #print(f"[DEBUG] Invoice Number (from 'Order Number' for Nite Ize Inc): {best['orig']}")
                    return best["orig"].lstrip("#:").strip()
    
    # Arc'teryx-specific logic: prioritize looking below labels to avoid years like "2025"
    if vendor_name == "Arc'teryx":
        logger.debug("Using Arc'teryx-specific logic: checking below labels first")
        max_distance_below = 150
        all_candidates = []
        
        # Collect candidates from both "Invoice" and "Credit" labels
        # Step 1: Check below "Invoice" labels
        for label_idx, (label_x0, label_x1, label_y) in enumerate(label_positions):
            for w in normalized_words:
                mid_x = (w["x0"] + w["x1"]) / 2
                vertical_distance = w["top"] - label_y
                
                # Arc'teryx invoice numbers should be 10 digits, not 4-digit years
                if (
                    label_x0 <= mid_x <= label_x1 and
                    0 < vertical_distance <= max_distance_below and
                    is_potential_invoice_number(w["text"], vendor_name) and
                    len(w["text"]) >= 10  # Exclude 4-digit years like "2025"
                ):
                    all_candidates.append({
                        'word': w,
                        'distance': vertical_distance,
                        'source': 'invoice_label',
                        'label_idx': label_idx
                    })
                    #print(f"[DEBUG] Arc'teryx candidate from invoice label {label_idx}: {w['orig']} (Δy={vertical_distance:.1f})")
        
        # Step 2: Check below "Credit" labels (some Arc'teryx files have invoice number there)
        credit_label_positions = []
        for idx, w in enumerate(normalized_words):
            if w["text"] == "credit":
                # Check if followed by "note" to make "Credit Note"
                if idx < len(normalized_words) - 1 and normalized_words[idx + 1]["text"] == "note":
                    next_word = normalized_words[idx + 1]
                    credit_label_positions.append((w["x0"], next_word["x1"], w["top"]))
                else:
                    # Just "Credit" by itself
                    credit_label_positions.append((w["x0"], w["x1"], w["top"]))
        
        for label_idx, (label_x0, label_x1, label_y) in enumerate(credit_label_positions):
            for w in normalized_words:
                mid_x = (w["x0"] + w["x1"]) / 2
                vertical_distance = w["top"] - label_y
                
                if (
                    label_x0 <= mid_x <= label_x1 and
                    0 < vertical_distance <= max_distance_below and
                    is_potential_invoice_number(w["text"], vendor_name) and
                    len(w["text"]) >= 10  # Exclude 4-digit years like "2025"
                ):
                    all_candidates.append({
                        'word': w,
                        'distance': vertical_distance,
                        'source': 'credit_label',
                        'label_idx': label_idx
                    })
                    #print(f"[DEBUG] Arc'teryx candidate from credit label {label_idx}: {w['orig']} (Δy={vertical_distance:.1f})")
        
        # Step 3: Choose the best candidate using smart logic
        if all_candidates:
            # Count occurrences of each number in the document
            number_counts = {}
            for w in normalized_words:
                if w["text"].isdigit() and len(w["text"]) >= 10:
                    number_counts[w["text"]] = number_counts.get(w["text"], 0) + 1
            
            # Score candidates: prefer numbers that appear less frequently (more unique)
            # and are closer to their respective labels
            best_candidate = None
            best_score = float("inf")
            
            for candidate in all_candidates:
                number = candidate['word']['text']
                frequency = number_counts.get(number, 1)
                distance = candidate['distance']
                
                # Lower score is better: prefer unique numbers (low frequency) and close distance
                # Frequency penalty: multiply by frequency to penalize duplicates
                # Distance penalty: add distance
                score = (frequency * 10) + distance
                
                #print(f"[DEBUG] Arc'teryx candidate: {number} (freq={frequency}, dist={distance:.1f}, score={score:.1f})")
                
                if score < best_score:
                    best_score = score
                    best_candidate = candidate['word']
            
            if best_candidate:
                #print(f"[DEBUG] Invoice Number (Arc'teryx smart logic): {best_candidate['orig']}")
                return best_candidate["orig"].lstrip("#:").strip()
    
    # Look for value to the right of any invoice label (strict)
    invoice_right_match = find_value_to_right(
        normalized_words, 
        label_positions,
        lambda text: is_potential_invoice_number(text, vendor_name),
        strict=True
    )
    if invoice_right_match:
        return invoice_right_match
    
    # Look with looser tolerances
    invoice_right_loose = find_value_to_right(
        normalized_words, 
        label_positions,
        lambda text: is_potential_invoice_number(text, vendor_name),
        strict=False
    )
    if invoice_right_loose:
        return invoice_right_loose
    
    # Look below labels
    max_distance_below = 150
    best_candidate = None
    best_score = float("inf")

    for label_idx, (label_x0, label_x1, label_y) in enumerate(label_positions):
        for w in normalized_words:
            mid_x = (w["x0"] + w["x1"]) / 2
            vertical_distance = w["top"] - label_y

            # Yakima-specific regex
            if vendor_name == "Yakima":
                yakima_regex = r"^[0-9]{2}[a-zA-Z]{2}[0-9]{7}$"
                if (
                    label_x0 <= mid_x <= label_x1 and
                    0 < vertical_distance <= max_distance_below
                ):
                    match = re.match(yakima_regex, w["text"], re.IGNORECASE)
                    if match:
                        #print(f"[DEBUG] Yakima candidate from label {label_idx}: {w['orig']} (Δy={vertical_distance:.1f})")
                        if vertical_distance < best_score:
                            best_score = vertical_distance
                            best_candidate = w

            # Generic case for other vendors
            elif (
                label_x0 <= mid_x <= label_x1 and
                0 < vertical_distance <= max_distance_below and
                is_potential_invoice_number(w["text"], vendor_name)
            ):
                #print(f"[DEBUG] Candidate from label {label_idx}: {w['orig']} (Δy={vertical_distance:.1f})")
                if vertical_distance < best_score:
                    best_score = vertical_distance
                    best_candidate = w

    if best_candidate:
        logger.debug(f"Invoice Number (below fallback best): {best_candidate['orig']}")
        return best_candidate["orig"].lstrip("#:").strip()

    logger.debug("No label match or fallback for Invoice Number.")
    return ""

def is_potential_invoice_number(text, vendor_name=None):
    logger.debug(f"Testing invoice candidate: '{text}' for vendor '{vendor_name}'")
    # Hydro Flask: accept digit sequences but exclude phone patterns
    if vendor_name == "Hydro Flask":
        # Exclude phone number patterns
        if re.match(r"^\d{3}-\d{3}-\d{4}$", text.strip()):
            return False
        # Accept sequences of digits (let general validation handle the rest)
        return re.match(r"^\d{5,}$", text.strip()) is not None
    # Helinox: must start with "INVUS" followed by digits
    if vendor_name == "Helinox":
        return re.match(r"^invus\d+$", text.strip(), re.IGNORECASE) is not None
    # Outdoor Research: match US.SI- followed by digits
    if vendor_name == "Outdoor Research":
        return re.match(r"^us\.si-\d+$", text.strip(), re.IGNORECASE) is not None
    # Oboz: must start with "csi" followed by digits
    if vendor_name == "Oboz Footwear LLC":
        return re.match(r"^csi\d+$", text.strip(), re.IGNORECASE) is not None
    # IceMule: must start with "inv"
    if vendor_name == "IceMule Company":
        return re.match(r"^inv-\d*$", text.strip(), re.IGNORECASE) is not None
    # Panache: must start with "panache-" followed by 5 digits
    if vendor_name == "Panache Apparel":
        return re.match(r"^panache-\d+$", text.strip(), re.IGNORECASE) is not None
    # Prana: only match a string of digits (no letters, slashes, or punctuation)
    if vendor_name == "Prana Living LLC":
        return re.match(r"^\d+$", text.strip()) is not None
    # Exclude any candidate starting with "XD-"
    if text.strip().upper().startswith("XD-"):
        return False
    # Gregory: must be number larger than 2 digits
    if vendor_name == "Gregory Mountain Products" or vendor_name == "Treadlabs":
        return re.match(
            r"^#?(?:[a-zA-Z]{1,4}-?)?[0-9]{3,}[a-zA-Z0-9\-]*$",
            text.strip(),
            re.IGNORECASE
        )
    # Scientific Anglers LLC: must start with "i-sa-" followed by digits
    if vendor_name == "Scientific Anglers LLC":
        return re.match(r"^i-sa-\d+$", text.strip(), re.IGNORECASE) is not None
    # Katin: must start with "usa-i" followed by digits
    if vendor_name == "KATIN":
        return re.match(r"^usa-i\d+$", text.strip(), re.IGNORECASE) is not None
    # General case:
    general_regex = (
        r"^#?(?:[a-zA-Z]{1,4}-?)?[0-9]{2,}[a-zA-Z0-9\-\/]*$"  # original pattern
        r"|^si\+\d{5,6}$"  # explicitly allow si-xxxxx or si-xxxxxx
    )
    return re.match(
        general_regex,
        text.strip(),
        re.IGNORECASE
    )