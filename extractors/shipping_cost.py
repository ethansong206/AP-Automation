import re
from .common_extraction import normalize_words

def extract_shipping_cost(words, vendor_name):
    """
    Simplified shipping cost extraction using exact Y-coordinate matching.
    No zone filtering, no percentage thresholds, no total amount dependency.
    """
    if not words:
        return ""

    # Credit memos and credit notes never have shipping costs (they're refunds/adjustments)
    # Use the discount terms extractor to properly identify document type
    from extractors.discount_terms import extract_discount_terms
    discount_terms = extract_discount_terms(words, vendor_name)
    if discount_terms and discount_terms.upper() in ['CREDIT MEMO', 'CREDIT NOTE']:
        return "0.00"
    
    # Vendor-specific handling for Confluence Outdoor Inc. and Leatherman Tools (Freight + Fuel Surcharge)
    if vendor_name in ["Confluence Outdoor Inc.", "Leatherman Tools"]:
        freight_fuel_result = _extract_freight_plus_fuel_cost(words, vendor_name)
        if freight_fuel_result is not None:
            return freight_fuel_result
    
    # Vendor-specific handling for vendors with shipping cost below label
    if vendor_name in ["Rio Products", "Seirus Innovation"]:
        rio_result = _extract_rio_shipping_cost(words, vendor_name)
        if rio_result is not None:
            return rio_result
    
    # Vendors that use multiple shipping line items that need to be summed
    MULTIPLE_SHIPPING_VENDORS = ["Jackson Kayak", "Johnson Outdoors"]
    
    if vendor_name in MULTIPLE_SHIPPING_VENDORS:
        multiple_result = _extract_multiple_shipping_costs(words, vendor_name)
        if multiple_result is not None:
            return multiple_result
    
    # Vendor-specific handling for Werner Paddles (only look for Freight, ignore Shipping)
    if vendor_name == "Werner Paddles":
        werner_result = _extract_werner_freight_cost(words, vendor_name)
        if werner_result is not None:
            return werner_result
    
    # Vendor-specific handling for Liberty Mountain (freight allowance deductions)
    if vendor_name == "Liberty Mountain Sports":
        liberty_result = _extract_liberty_mountain_shipping_cost(words, vendor_name)
        if liberty_result is not None:
            return liberty_result
    
    # Use multi-page reading for all vendors (no restrictions)
    normalized_words = normalize_words(words, first_page_only=False)
    
    if not normalized_words:
        return "0.00"
    
    # Primary shipping labels to look for
    shipping_labels = [
        "shipping", "freight", "frt", "ship", "delivery", "handling", "additional", "postage"
    ]

    if vendor_name == "Hestra Gloves, LLC":
        shipping_labels.append("fedex")
    
    def find_shipping_labels_all_zones():
        """Find shipping label positions without zone restrictions"""
        shipping_label_positions = []

        # Single word labels and slash-separated compound labels
        for word in normalized_words:
            word_text = word["text"].lower().rstrip(":")

            # Check for exact single word match
            if word_text in shipping_labels and not _is_ship_to_label(word, normalized_words):
                shipping_label_positions.append({
                    "x0": word["x0"],
                    "x1": word["x1"],
                    "top": word["top"],
                    "bottom": word["bottom"],
                    "label": word["text"],
                    "page_num": word["page_num"]
                })
            # Check for slash-separated compound labels (e.g., "shipping/handling", "freight/delivery")
            elif "/" in word_text:
                parts = word_text.split("/")
                if any(part.strip() in shipping_labels for part in parts):
                    shipping_label_positions.append({
                        "x0": word["x0"],
                        "x1": word["x1"], 
                        "top": word["top"],
                        "bottom": word["bottom"],
                        "label": word["text"],
                        "page_num": word["page_num"]
                    })
        
        # Multi-word labels (e.g., "Shipping Cost", "Additional Freight")
        for idx in range(len(normalized_words) - 1):
            first_word = normalized_words[idx]
            second_word = normalized_words[idx + 1]
            
            # Check if first word is a shipping term
            if first_word["text"].lower() in shipping_labels:
                # Check if second word is likely part of shipping label
                second_text = second_word["text"].lower()
                if second_text in ["cost", "costs", "charge", "charges", "fee", "fees", "amount", "freight"]:
                    # Combine the two words as a single label
                    shipping_label_positions.append({
                        "x0": first_word["x0"],
                        "x1": second_word["x1"],
                        "top": first_word["top"],
                        "bottom": max(first_word["bottom"], second_word["bottom"]),
                        "label": f"{first_word['text']} {second_word['text']}",
                        "page_num": first_word["page_num"]
                    })
        
        return shipping_label_positions
    
    def search_for_shipping_values(shipping_label_positions):
        """Search for shipping values using exact Y-coordinate matching"""
        for label_pos in shipping_label_positions:
            candidates = []

            # Get the page number directly from the label position
            label_page = label_pos.get("page_num", 0)

            for word in normalized_words:
                # Get the page number directly from the normalized word
                word_page = word.get("page_num", 0)

                # Skip if they're on different pages
                if label_page != word_page:
                    continue

                # Check if word is to the right of label with exact Y-coordinate alignment
                horizontal_distance = word["x0"] - label_pos["x1"]
                vertical_distance = abs(word["top"] - label_pos["top"])

                # Exact Y-coordinate matching with minimal tolerance
                if (20 <= horizontal_distance <= 700 and  # Extended horizontal distance
                    vertical_distance <= 2 and           # Exact Y-alignment (±2px tolerance)
                    is_potential_shipping_cost(word["text"]) and
                    not _is_near_weight_text(word, normalized_words) and
                    not _is_near_insurance_text(word, normalized_words)):

                    candidates.append({
                        "word": word,
                        "h_dist": horizontal_distance,
                        "v_dist": vertical_distance,
                        "label": label_pos["label"],
                        "score": horizontal_distance + (vertical_distance * 10)  # Prioritize Y-alignment
                    })
            
            # Return the best candidate with preference for rightmost when perfectly aligned
            if candidates:
                # Check if we have multiple candidates with perfect vertical alignment
                perfect_alignment_candidates = [c for c in candidates if c["v_dist"] <= 2]
                
                if len(perfect_alignment_candidates) > 1:
                    # Multiple perfectly aligned candidates - prefer rightmost (highest h_dist)
                    sorted_candidates = sorted(perfect_alignment_candidates, key=lambda x: x["h_dist"], reverse=True)
                else:
                    # Single candidate or no perfect alignment - use original closest logic
                    sorted_candidates = sorted(candidates, key=lambda x: x["score"])
                
                for candidate in sorted_candidates:
                    extracted_value = clean_currency_value(candidate["word"]["text"])
                    if extracted_value:
                        # Vendor-specific exclusions
                        if vendor_name == "Prana Living LLC" and extracted_value == "25.00":
                            continue  # Skip $25.00 for Prana (likely flat fee, not shipping)
                        
                        # Check if there's a negative amount that cancels out this shipping cost
                        if _has_negative_cancellation(extracted_value, normalized_words, candidate["word"]):
                            return "0.00"  # Shipping is cancelled out
                        return extracted_value
        
        # No results found
        return None
    
    # Find shipping labels and search for values
    shipping_labels = find_shipping_labels_all_zones()
    result = search_for_shipping_values(shipping_labels)

    if result:
        return result

    # If no shipping cost found, default to 0.00
    return "0.00"

def _extract_freight_plus_fuel_cost(words, vendor_name):
    """
    Extract and sum FREIGHT + FUEL costs for vendors that split shipping charges.
    Handles different label formats for Confluence and Leatherman Tools.
    Returns formatted shipping cost string or None if no shipping found.
    """
    # Build full text from all words
    full_text = ' '.join([word.get('text', '') for word in words])
    
    if vendor_name == "Confluence Outdoor Inc.":
        # Confluence patterns: "FREIGHT: $15.00" and "FUEL SURCHARGE: $5.00"
        freight_pattern = r'FREIGHT:\s*\$?\s*([\d,]+\.?\d{0,2})'
        fuel_pattern = r'FUEL\s+SURCHARGE:\s*\$?\s*([\d,]+\.?\d{0,2})'
    
    elif vendor_name == "Leatherman Tools":
        # Leatherman patterns: "Rate FREIGHT for carrier: UPS $15.00" and "Rate FUEL for carrier: UPS $5.00"
        freight_pattern = r'Rate\s+FREIGHT\s+for\s+carrier:?\s*\w+\s*\$?\s*([\d,]+\.?\d{0,2})'
        fuel_pattern = r'Rate\s+FUEL\s+for\s+carrier:?\s*\w+\s*\$?\s*([\d,]+\.?\d{0,2})'
    
    else:
        return None
    
    # Extract freight amounts
    freight_matches = re.findall(freight_pattern, full_text, re.IGNORECASE)
    freight_total = sum(float(match.replace(',', '')) for match in freight_matches)
    
    # Extract fuel surcharge amounts  
    fuel_matches = re.findall(fuel_pattern, full_text, re.IGNORECASE)
    fuel_total = sum(float(match.replace(',', '')) for match in fuel_matches)
    
    # Calculate total shipping cost
    total_shipping = freight_total + fuel_total
    
    # Return formatted result
    return f"{total_shipping:.2f}"

def _extract_werner_freight_cost(words, vendor_name):
    """
    Extract shipping cost for Werner Paddles using only "Freight" labels (ignore "Shipping").
    Werner Paddles has freight values in the cost summary that should be used instead of 
    shipping labels that may show 0.00.
    Returns formatted shipping cost string or None if no freight found.
    """
    # Use multi-page reading
    normalized_words = normalize_words(words, first_page_only=False)
    
    if not normalized_words:
        return None
    
    # Only look for freight labels (exclude shipping, delivery, handling, etc.)
    freight_labels = ["freight"]
    
    # Find freight label positions
    freight_label_positions = []
    
    for word in normalized_words:
        word_text = word["text"].lower().rstrip(":")
        
        # Check for exact freight match only
        if word_text in freight_labels:
            freight_label_positions.append({
                "x0": word["x0"],
                "x1": word["x1"], 
                "top": word["top"],
                "bottom": word["bottom"],
                "label": word["text"],
                "page_num": word["page_num"]
            })
    
    # Search for freight values using same logic as main extractor
    for label_pos in freight_label_positions:
        candidates = []
        label_page = label_pos.get("page_num", 0)
        
        for word in normalized_words:
            word_page = word.get("page_num", 0)
            
            # Skip if they're on different pages
            if label_page != word_page:
                continue
            
            # Check if word is to the right of label with exact Y-coordinate alignment
            horizontal_distance = word["x0"] - label_pos["x1"]
            vertical_distance = abs(word["top"] - label_pos["top"])
            
            # Same exact matching criteria as main extractor
            if (20 <= horizontal_distance <= 700 and  # Extended horizontal distance
                vertical_distance <= 2 and           # Exact Y-alignment (±2px tolerance)
                is_potential_shipping_cost(word["text"]) and
                not _is_near_weight_text(word, normalized_words) and
                not _is_near_insurance_text(word, normalized_words)):
                
                candidates.append({
                    "word": word,
                    "h_dist": horizontal_distance,
                    "v_dist": vertical_distance,
                    "label": label_pos["label"],
                    "score": horizontal_distance + (vertical_distance * 10)
                })
        
        # Return the best candidate (rightmost preference for perfect alignment)
        if candidates:
            # Check if we have multiple candidates with perfect vertical alignment
            perfect_alignment_candidates = [c for c in candidates if c["v_dist"] <= 2]
            
            if len(perfect_alignment_candidates) > 1:
                # Multiple perfectly aligned candidates - prefer rightmost (highest h_dist)
                sorted_candidates = sorted(perfect_alignment_candidates, key=lambda x: x["h_dist"], reverse=True)
            else:
                # Single candidate or no perfect alignment - use original closest logic
                sorted_candidates = sorted(candidates, key=lambda x: x["score"])
            
            for candidate in sorted_candidates:
                extracted_value = clean_currency_value(candidate["word"]["text"])
                if extracted_value:
                    # Vendor-specific exclusions (applied to Werner Paddles as well)
                    if vendor_name == "Prana Living LLC" and extracted_value == "25.00":
                        continue  # Skip $25.00 for Prana (likely flat fee, not shipping)
                    
                    # Check if there's a negative amount that cancels out this freight cost
                    if _has_negative_cancellation(extracted_value, normalized_words, candidate["word"]):
                        return "0.00"  # Freight is cancelled out
                    return extracted_value
    
    # No freight found
    return None

def _extract_liberty_mountain_shipping_cost(words, vendor_name):
    """
    Extract shipping cost for Liberty Mountain Sports with freight allowance deductions.
    Handles lines like "DEDUCT FREIGHT ALLOWANCE* OF $ 62.52" that should be subtracted
    from the base shipping cost. Ignores "DEDUCT PROMPT PAYMENT DISCOUNT" lines.
    Returns formatted shipping cost string or None if no shipping found.
    """
    # Build full text from all words
    full_text = ' '.join([word.get('text', '') for word in words])
    
    # Use multi-page reading
    normalized_words = normalize_words(words, first_page_only=False)
    
    if not normalized_words:
        return None
    
    # First, extract base shipping cost using standard logic
    shipping_labels = ["shipping", "freight", "frt", "ship", "delivery", "handling", "postage"]
    base_shipping_cost = 0.0
    
    # Find shipping label positions
    shipping_label_positions = []
    
    for word in normalized_words:
        word_text = word["text"].lower().rstrip(":")
        
        # Check for exact single word match
        if word_text in shipping_labels and not _is_ship_to_label(word, normalized_words):
            shipping_label_positions.append({
                "x0": word["x0"],
                "x1": word["x1"], 
                "top": word["top"],
                "bottom": word["bottom"],
                "label": word["text"],
                "page_num": word["page_num"]
            })
        # Check for slash-separated compound labels
        elif "/" in word_text:
            parts = word_text.split("/")
            if any(part.strip() in shipping_labels for part in parts):
                shipping_label_positions.append({
                    "x0": word["x0"],
                    "x1": word["x1"], 
                    "top": word["top"],
                    "bottom": word["bottom"],
                    "label": word["text"],
                    "page_num": word["page_num"]
                })
    
    # Extract base shipping cost using standard horizontal matching
    for label_pos in shipping_label_positions:
        candidates = []
        label_page = label_pos.get("page_num", 0)
        
        for word in normalized_words:
            word_page = word.get("page_num", 0)
            
            # Skip if they're on different pages
            if label_page != word_page:
                continue
            
            # Check if word is to the right of label with exact Y-coordinate alignment
            horizontal_distance = word["x0"] - label_pos["x1"]
            vertical_distance = abs(word["top"] - label_pos["top"])
            
            # Same exact matching criteria as main extractor
            if (20 <= horizontal_distance <= 700 and  # Extended horizontal distance
                vertical_distance <= 2 and           # Exact Y-alignment (±2px tolerance)
                is_potential_shipping_cost(word["text"]) and
                not _is_near_weight_text(word, normalized_words) and
                not _is_near_insurance_text(word, normalized_words)):
                
                candidates.append({
                    "word": word,
                    "h_dist": horizontal_distance,
                    "v_dist": vertical_distance,
                    "label": label_pos["label"],
                    "score": horizontal_distance + (vertical_distance * 10)
                })
        
        # Get the best candidate for this label
        if candidates:
            # Check if we have multiple candidates with perfect vertical alignment
            perfect_alignment_candidates = [c for c in candidates if c["v_dist"] <= 2]
            
            if len(perfect_alignment_candidates) > 1:
                # Multiple perfectly aligned candidates - prefer rightmost (highest h_dist)
                sorted_candidates = sorted(perfect_alignment_candidates, key=lambda x: x["h_dist"], reverse=True)
            else:
                # Single candidate or no perfect alignment - use original closest logic
                sorted_candidates = sorted(candidates, key=lambda x: x["score"])
            
            for candidate in sorted_candidates:
                extracted_value = clean_currency_value(candidate["word"]["text"])
                if extracted_value:
                    # Convert to float for calculation
                    try:
                        base_shipping_cost = float(extracted_value)
                        break  # Found base shipping cost
                    except ValueError:
                        continue
        
        if base_shipping_cost > 0:
            break  # Found base shipping cost, stop looking
    
    # Now look for freight allowance deductions (ignore prompt payment discounts)
    freight_allowance_pattern = r'DEDUCT\s+FREIGHT\s+ALLOWANCE[^$]*\$\s*([\d,]+\.?\d{0,2})'
    freight_allowance_matches = re.findall(freight_allowance_pattern, full_text, re.IGNORECASE)
    
    # Calculate total freight allowance deductions
    total_deductions = sum(float(match.replace(',', '')) for match in freight_allowance_matches)
    
    # Calculate final shipping cost
    final_shipping_cost = max(0.0, base_shipping_cost - total_deductions)
    
    # Return formatted result
    return f"{final_shipping_cost:.2f}"

def _extract_rio_shipping_cost(words, vendor_name):
    """
    Extract shipping cost for Rio Products where the value appears directly below the shipping label.
    Returns formatted shipping cost string or None if no shipping found.
    """
    # Use multi-page reading for Rio Products
    normalized_words = normalize_words(words, first_page_only=False)
    
    if not normalized_words:
        return None
    
    # Primary shipping labels to look for
    shipping_labels = ["shipping", "freight", "frt", "ship", "delivery", "handling", "postage"]
    
    # Find shipping label positions
    shipping_label_positions = []
    
    for word in normalized_words:
        word_text = word["text"].lower().rstrip(":")
        
        # Check for exact single word match
        if word_text in shipping_labels and not _is_ship_to_label(word, normalized_words):
            shipping_label_positions.append({
                "x0": word["x0"],
                "x1": word["x1"], 
                "top": word["top"],
                "bottom": word["bottom"],
                "label": word["text"],
                "page_num": word["page_num"]
            })
        # Check for slash-separated compound labels (e.g., "shipping/handling", "freight/delivery")
        elif "/" in word_text:
            parts = word_text.split("/")
            if any(part.strip() in shipping_labels for part in parts):
                shipping_label_positions.append({
                    "x0": word["x0"],
                    "x1": word["x1"], 
                    "top": word["top"],
                    "bottom": word["bottom"],
                    "label": word["text"],
                    "page_num": word["page_num"]
                })
    
    # Search for shipping values directly below labels
    for label_pos in shipping_label_positions:
        candidates = []
        label_page = label_pos.get("page_num", 0)
        
        for word in normalized_words:
            word_page = word.get("page_num", 0)
            
            # Skip if they're on different pages
            if label_page != word_page:
                continue
            
            # Check if word is below the label (Y-coordinate logic)
            # Below means higher top value (PDFs have origin at bottom-left)
            vertical_distance = word["top"] - label_pos["bottom"]
            horizontal_alignment = abs(word["x0"] - label_pos["x0"])
            
            # Rio Products: value directly below label (skip weight filtering due to table layout)
            if (0 <= vertical_distance <= 50 and        # Within 50px below label
                horizontal_alignment <= 30 and          # Horizontally aligned (±30px)
                is_potential_shipping_cost(word["text"]) and
                not _is_near_insurance_text(word, normalized_words)):
                
                candidates.append({
                    "word": word,
                    "v_dist": vertical_distance,
                    "h_align": horizontal_alignment,
                    "label": label_pos["label"],
                    "score": vertical_distance + (horizontal_alignment * 2)  # Prioritize closer vertically and horizontally
                })
        
        # Return the best candidate (closest below)
        if candidates:
            sorted_candidates = sorted(candidates, key=lambda x: x["score"])
            
            for candidate in sorted_candidates:
                extracted_value = clean_currency_value(candidate["word"]["text"])
                if extracted_value:
                    # Vendor-specific exclusions (applied to Rio Products as well)
                    if vendor_name == "Prana Living LLC" and extracted_value == "25.00":
                        continue  # Skip $25.00 for Prana (likely flat fee, not shipping)
                    
                    # Check if there's a negative amount that cancels out this shipping cost
                    if _has_negative_cancellation(extracted_value, normalized_words, candidate["word"]):
                        return "0.00"  # Shipping is cancelled out
                    return extracted_value
    
    # No results found
    return None

def _extract_multiple_shipping_costs(words, vendor_name):
    """
    Extract and sum multiple shipping line items for vendors that charge shipping per line item.
    Returns formatted total shipping cost string or None if no shipping found.
    """
    # Use multi-page reading
    normalized_words = normalize_words(words, first_page_only=False)
    
    if not normalized_words:
        return None
    
    # Primary shipping labels to look for
    shipping_labels = ["shipping", "freight", "frt", "ship", "delivery", "handling", "postage"]
    
    # Find all shipping labels
    shipping_label_positions = []
    
    for word in normalized_words:
        word_text = word["text"].lower().rstrip(":")
        
        # Check for exact single word match
        if word_text in shipping_labels and not _is_ship_to_label(word, normalized_words):
            shipping_label_positions.append({
                "x0": word["x0"],
                "x1": word["x1"], 
                "top": word["top"],
                "bottom": word["bottom"],
                "label": word["text"],
                "page_num": word["page_num"]
            })
        # Check for slash-separated compound labels (e.g., "shipping/handling", "freight/delivery")
        elif "/" in word_text:
            parts = word_text.split("/")
            if any(part.strip() in shipping_labels for part in parts):
                shipping_label_positions.append({
                    "x0": word["x0"],
                    "x1": word["x1"], 
                    "top": word["top"],
                    "bottom": word["bottom"],
                    "label": word["text"],
                    "page_num": word["page_num"]
                })
    
    # Collect all shipping costs found
    shipping_costs = []
    used_y_coordinates = []  # Track Y-coordinates where we've already extracted values
    
    # Search for shipping values for each label
    for label_pos in shipping_label_positions:
        candidates = []
        label_page = label_pos.get("page_num", 0)
        
        for word in normalized_words:
            word_page = word.get("page_num", 0)
            
            # Skip if they're on different pages
            if label_page != word_page:
                continue
            
            # Check if word is to the right of label with exact Y-coordinate alignment
            horizontal_distance = word["x0"] - label_pos["x1"]
            vertical_distance = abs(word["top"] - label_pos["top"])
            
            # Same exact matching criteria as main extractor
            if (20 <= horizontal_distance <= 700 and  # Extended horizontal distance
                vertical_distance <= 2 and           # Exact Y-alignment (±2px tolerance)
                is_potential_shipping_cost(word["text"]) and
                not _is_near_weight_text(word, normalized_words) and
                not _is_near_insurance_text(word, normalized_words)):
                
                candidates.append({
                    "word": word,
                    "h_dist": horizontal_distance,
                    "v_dist": vertical_distance,
                    "label": label_pos["label"],
                    "score": horizontal_distance + (vertical_distance * 10)
                })
        
        # Find the best candidate for this label (only ONE value per label)
        if candidates:
            # Check if we have multiple candidates with perfect vertical alignment
            perfect_alignment_candidates = [c for c in candidates if c["v_dist"] <= 2]
            
            if len(perfect_alignment_candidates) > 1:
                # Multiple perfectly aligned candidates - prefer rightmost (highest h_dist)
                sorted_candidates = sorted(perfect_alignment_candidates, key=lambda x: x["h_dist"], reverse=True)
            else:
                # Single candidate or no perfect alignment - use original closest logic
                sorted_candidates = sorted(candidates, key=lambda x: x["score"])
            
            # Take only the FIRST valid candidate for this label, and avoid double-counting same Y-coordinate
            for candidate in sorted_candidates:
                candidate_y = candidate["word"]["top"]
                candidate_page = candidate["word"].get("page_num", 0)
                
                # Check if we've already extracted a value from this Y-coordinate on this page
                coordinate_key = (candidate_page, round(candidate_y, 1))  # Round to avoid floating point precision issues
                if coordinate_key in used_y_coordinates:
                    continue  # Skip this candidate, we already got a value from this line
                
                extracted_value = clean_currency_value(candidate["word"]["text"])
                if extracted_value:
                    # Vendor-specific exclusions (applied to multiple shipping as well)
                    if vendor_name == "Prana Living LLC" and extracted_value == "25.00":
                        continue  # Skip $25.00 for Prana (likely flat fee, not shipping)
                    
                    # Convert to float for summing
                    try:
                        cost_float = float(extracted_value)
                        shipping_costs.append(cost_float)
                        used_y_coordinates.append(coordinate_key)  # Mark this Y-coordinate as used
                        break  # CRITICAL: Only one value per shipping label
                    except ValueError:
                        continue
            # If we reach here, no valid candidate was found for this label
    
    # Sum all shipping costs found
    if shipping_costs:
        total_shipping = sum(shipping_costs)
        
        # Check if there's a negative cancellation for the total
        total_formatted = f"{total_shipping:.2f}"
        
        # For negative cancellation check, we need a dummy word object
        # We'll use the first shipping label position as reference
        if shipping_label_positions:
            dummy_word = {
                "page_num": shipping_label_positions[0]["page_num"],
                "x0": shipping_label_positions[0]["x0"],
                "top": shipping_label_positions[0]["top"]
            }
            
            if _has_negative_cancellation(total_formatted, normalized_words, dummy_word):
                return "0.00"  # All shipping is cancelled out
        
        return total_formatted
    
    # No shipping costs found
    return None

def _is_near_insurance_text(candidate_word, normalized_words):
    """
    Check if a candidate shipping cost value is near insurance-related text.
    This helps avoid extracting insurance amounts as shipping costs (e.g., Columbia's "$2 million" clause).
    """
    # Look for insurance-related terms within proximity of the candidate
    insurance_terms = ["insurance", "liability", "million", "aggregate", "occurrence", "insured"]
    
    candidate_x = candidate_word["x0"]
    candidate_y = candidate_word["top"]
    candidate_page = candidate_word.get("page_num", 0)
    
    for word in normalized_words:
        # Only check words on the same page
        if word.get("page_num", 0) != candidate_page:
            continue
            
        word_text = word["text"].lower()
        
        # Check if this word contains insurance-related terms
        if any(term in word_text for term in insurance_terms):
            # Calculate proximity
            horizontal_distance = abs(word["x0"] - candidate_x)
            vertical_distance = abs(word["top"] - candidate_y)
            
            # Consider "near" if within reasonable proximity
            # Horizontal: within 300px, Vertical: within 50px (wider than weight terms due to legal text layout)
            if horizontal_distance <= 300 and vertical_distance <= 50:
                return True
    
    return False

def _is_near_weight_text(candidate_word, normalized_words):
    """
    Check if a candidate shipping cost value is near 'WEIGHT' text.
    This helps avoid extracting weight values as shipping costs (e.g., Birkenstock invoices).
    """
    # Look for weight-related terms within proximity of the candidate
    weight_terms = ["weight", "wt", "lbs", "pounds", "kg", "total weight"]
    
    candidate_x = candidate_word["x0"]
    candidate_y = candidate_word["top"]
    candidate_page = candidate_word.get("page_num", 0)
    
    for word in normalized_words:
        # Only check words on the same page
        if word.get("page_num", 0) != candidate_page:
            continue
            
        word_text = word["text"].lower()
        
        # Check if this word contains weight-related terms
        if any(term in word_text for term in weight_terms):
            # Calculate proximity
            horizontal_distance = abs(word["x0"] - candidate_x)
            vertical_distance = abs(word["top"] - candidate_y)
            
            # Consider "near" if within reasonable proximity
            # Horizontal: within 200px, Vertical: within 30px
            if horizontal_distance <= 200 and vertical_distance <= 30:
                return True
    
    return False

def is_potential_shipping_cost(text):
    """
    Check if text could be a shipping cost value.
    IMPORTANT: Allow 0.00 values - they represent legitimate "no shipping charge"
    """
    # Must have currency symbol or decimal point to be considered a monetary value
    if not ('$' in text or '.' in text):
        return False
    
    # Remove whitespace and common prefixes
    clean_text = text.strip().lstrip("$").replace(",", "").replace(" ", "")
    
    # Must be numeric with optional decimal
    if not re.match(r'^\d+\.?\d{0,2}$', clean_text):
        return False
    
    # Convert to float for range checking
    try:
        value = float(clean_text)
        # Include 0.00 as valid shipping cost (no shipping)
        # No upper limit - let legitimate high shipping costs through
        return 0.0 <= value <= 99999.99
    except ValueError:
        return False

def clean_currency_value(text):
    """
    Clean and standardize currency values.
    Returns clean numeric string or empty string if invalid.
    """
    if not text:
        return ""
    
    # Remove currency symbols and whitespace
    clean = text.strip().lstrip("$").replace(",", "").replace(" ", "")
    
    # Validate format
    if re.match(r'^\d+\.?\d{0,2}$', clean):
        # Ensure proper decimal formatting
        if '.' not in clean:
            clean += '.00'
        elif len(clean.split('.')[1]) == 1:
            clean += '0'
        return clean
    
    return ""

def _has_negative_cancellation(shipping_amount, normalized_words, shipping_word):
    """
    Check if there's a negative amount that exactly cancels out the shipping cost.
    This handles cases where invoices show shipping charge + negative adjustment = free shipping.
    """
    if not shipping_amount:
        return False
    
    # Convert shipping amount to float for comparison
    try:
        shipping_value = float(shipping_amount)
    except ValueError:
        return False
    
    # Get the page of the shipping word for context
    shipping_page = shipping_word.get("page_num", 0)
    
    # Look for negative amounts on the same page
    for word in normalized_words:
        # Only check words on the same page
        if word.get("page_num", 0) != shipping_page:
            continue
        
        word_text = word["text"].strip()
        
        # Look for negative currency values (with minus sign or parentheses)
        negative_patterns = [
            rf'-\s*\$?\s*{re.escape(shipping_amount)}',  # -$15.00 or -15.00
            rf'\(\s*\$?\s*{re.escape(shipping_amount)}\s*\)',  # ($15.00) or (15.00)
            rf'-\s*{re.escape(shipping_amount)}',  # -15.00
            rf'\(\s*{re.escape(shipping_amount)}\s*\)'  # (15.00)
        ]
        
        # Check if this word matches any negative pattern
        for pattern in negative_patterns:
            if re.search(pattern, word_text, re.IGNORECASE):
                # Found a matching negative amount - shipping is cancelled
                return True
    
    return False

def _is_ship_to_label(ship_word, normalized_words):
    """
    Check if a "ship" word is part of "Ship To" address label rather than shipping cost label.
    Returns True if this should be excluded as a shipping cost label.
    """
    ship_page = ship_word.get("page_num", 0)
    ship_text = ship_word["text"].lower().rstrip(":")
    
    # Only check "ship" words, not other shipping terms
    if ship_text != "ship":
        return False
    
    # Look for "to" word that immediately follows "ship"
    for word in normalized_words:
        # Skip if different page
        if word.get("page_num", 0) != ship_page:
            continue
            
        word_text = word["text"].lower().rstrip(":")
        
        # Must be exactly "to" (not "total", "together", etc.)
        if word_text == "to":
            # Check if "to" immediately follows "ship" on the same line
            horizontal_distance = word["x0"] - ship_word["x1"]
            vertical_distance = abs(word["top"] - ship_word["top"])
            
            # "To" must be immediately to the right of "Ship" on same line
            if (0 <= horizontal_distance <= 50 and  # Close horizontally (right of Ship)
                vertical_distance <= 5):             # Same line (tight vertical tolerance)
                return True  # This is "Ship To", exclude it
    
    return False