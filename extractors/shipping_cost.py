import re
from .common_extraction import (
    normalize_words,
    find_label_positions,
    find_value_to_right
)

def extract_shipping_cost(words, vendor_name):
    """
    Extract shipping cost from document.
    Based on analysis of invoice patterns, shipping costs typically appear in:
    1. Bottom summary section (70-100% down the page)
    2. To the right of shipping labels (100-200px distance)
    3. Same horizontal line as the label (within 10px tolerance)
    """
    if not words:
        return ""
    
    # Vendors that require multi-page shipping extraction (shipping info on later pages)
    MULTI_PAGE_SHIPPING_VENDORS = [
        "Liberty Mountain Sports",
        # Add other vendors here as needed in the future
    ]
    
    # Use multi-page reading for specific vendors, first-page-only for others
    use_multi_page = vendor_name in MULTI_PAGE_SHIPPING_VENDORS
    normalized_words = normalize_words(words, first_page_only=not use_multi_page)
    
    # Get document bounds for threshold calculations
    if not normalized_words:
        return "0.00"
    
    max_y = max(w["bottom"] for w in normalized_words)
    
    # Primary shipping labels to look for
    shipping_labels = [
        "shipping", "freight", "ship", "delivery", "handling", "additional"
    ]
    
    # Try primary threshold first (60%), then fallback to secondary (40%) if no results
    primary_threshold = max_y * 0.6    # Bottom 40% of document
    fallback_threshold = max_y * 0.4   # Bottom 60% of document
    
    def find_shipping_labels_in_zone(threshold):
        """Find shipping label positions within a given threshold zone"""
        shipping_label_positions = []
        
        # Single word labels
        for idx, word in enumerate(normalized_words):
            if (word["text"].lower().rstrip(":") in shipping_labels and 
                word["top"] >= threshold):
                shipping_label_positions.append({
                    "x0": word["x0"],
                    "x1": word["x1"], 
                    "top": word["top"],
                    "bottom": word["bottom"],
                    "label": word["text"]
                })
        
        # Multi-word labels (e.g., "Shipping Cost", "Additional Freight")
        for idx in range(len(normalized_words) - 1):
            first_word = normalized_words[idx]
            second_word = normalized_words[idx + 1]
            
            # Check if first word is a shipping term and in threshold zone
            if (first_word["text"].lower() in shipping_labels and 
                first_word["top"] >= threshold):
                
                # Check if second word is likely part of shipping label
                second_text = second_word["text"].lower()
                if second_text in ["cost", "costs", "charge", "charges", "fee", "fees", "amount", "freight"]:
                    # Combine the two words as a single label
                    shipping_label_positions.append({
                        "x0": first_word["x0"],
                        "x1": second_word["x1"],
                        "top": first_word["top"],
                        "bottom": max(first_word["bottom"], second_word["bottom"]),
                        "label": f"{first_word['text']} {second_word['text']}"
                    })
        
        return shipping_label_positions
    
    def search_for_shipping_values(shipping_label_positions):
        """Search for shipping values near the found labels"""
        for label_pos in shipping_label_positions:
            candidates = []
            
            # Get the page number of the label for multi-page matching
            label_page = None
            for original_word in words:
                if (abs(original_word.get("x0", 0) - label_pos["x0"]) <= 1 and 
                    abs(original_word.get("top", 0) - label_pos["top"]) <= 1):
                    label_page = original_word.get("page_num", 0)
                    break
            
            for word in normalized_words:
                # Find the corresponding original word to get page number
                word_page = None
                for original_word in words:
                    if (abs(original_word.get("x0", 0) - word.get("x0", 0)) <= 1 and 
                        abs(original_word.get("top", 0) - word.get("top", 0)) <= 1):
                        word_page = original_word.get("page_num", 0)
                        break
                
                # Skip if we can't determine pages or if they're on different pages
                if label_page is None or word_page is None or label_page != word_page:
                    continue
                
                # Check if word is to the right of label (horizontal layout)
                horizontal_distance = word["x0"] - label_pos["x1"]
                vertical_distance = abs(word["top"] - label_pos["top"])
                
                # Check if word is below the label (vertical/stacked layout)
                vertical_down_distance = word["top"] - label_pos["bottom"]
                horizontal_alignment = abs(word["x0"] - label_pos["x0"])
                
                # Spatial criteria for horizontal layout (original pattern)
                # Extended range to handle Yeti's tighter spacing (20px) and other vendors
                if (20 <= horizontal_distance <= 250 and  # 20-250px range to handle various vendors
                    vertical_distance <= 15 and           # Same line tolerance
                    is_potential_shipping_cost(word["text"])):
                    
                    candidates.append({
                        "word": word,
                        "h_dist": horizontal_distance,
                        "v_dist": vertical_distance,
                        "label": label_pos["label"],
                        "layout": "horizontal",
                        "score": horizontal_distance + (vertical_distance * 2)  # Prioritize vertical alignment
                    })
                
                # Spatial criteria for vertical layout (Far Bank pattern)
                elif (0 <= vertical_down_distance <= 25 and    # Below the label within reasonable distance
                      horizontal_alignment <= 50 and          # Reasonably aligned horizontally
                      is_potential_shipping_cost(word["text"])):
                    
                    candidates.append({
                        "word": word,
                        "v_down_dist": vertical_down_distance,
                        "h_align": horizontal_alignment,
                        "label": label_pos["label"],
                        "layout": "vertical", 
                        "score": vertical_down_distance + horizontal_alignment  # Prioritize close vertical and horizontal alignment
                    })
            
            # Return the best candidate (closest with priority on alignment)
            if candidates:
                # Sort candidates by score and validate them
                sorted_candidates = sorted(candidates, key=lambda x: x["score"])
                
                for candidate in sorted_candidates:
                    extracted_value = clean_currency_value(candidate["word"]["text"])
                    if extracted_value:
                        # Additional validation: if the extracted value seems too large compared to 
                        # typical shipping costs, it might be a false positive (like total amount)
                        try:
                            value_float = float(extracted_value)
                            # Get horizontal distance based on layout type
                            if candidate["layout"] == "horizontal":
                                h_dist = candidate.get("h_dist", 0)
                            else:  # vertical layout
                                h_dist = candidate.get("h_align", 0)  # Use horizontal alignment as proxy for distance
                            
                            # Vendor-specific filter for Olukai: reject total invoice amounts
                            if vendor_name == "Olukai LLC":
                                candidate_x = candidate["word"]["x0"]
                                candidate_y = candidate["word"]["top"]
                                
                                # Look for "TOTAL INVOICE" combination specifically (Olukai pattern)
                                near_total_invoice = False
                                for i, word in enumerate(normalized_words):
                                    if word["text"].lower() == "total":
                                        # Check if next word is "invoice"
                                        if i + 1 < len(normalized_words) and normalized_words[i + 1]["text"].lower() == "invoice":
                                            total_invoice_x = word["x0"]
                                            total_invoice_y = word["top"]
                                            
                                            # Check if candidate is close to "TOTAL INVOICE"
                                            x_distance = abs(candidate_x - total_invoice_x)
                                            y_distance = abs(candidate_y - total_invoice_y)
                                            
                                            # Within 200px horizontally and 20px vertically
                                            if x_distance <= 200 and y_distance <= 20:
                                                near_total_invoice = True
                                                break
                                
                                # For Olukai: reject if near "TOTAL INVOICE" and amount is substantial (>$200)
                                if near_total_invoice and value_float > 200:
                                    continue
                            
                            # Stronger false positive filters:
                            # 1. Very large amounts (>$700) are likely invoice totals
                            if value_float > 700:
                                continue
                            # 2. Medium amounts with very close horizontal distance might be totals/subtotals
                            # Use relaxed filter for Liberty Mountain due to their specific layout
                            elif vendor_name == "Liberty Mountain Sports":
                                # Very relaxed filter for Liberty Mountain: only reject very large amounts very close
                                if value_float > 200 and h_dist < 30:
                                    continue
                            elif vendor_name == "Yeti Coolers":
                                # Relaxed filter for Yeti: allow legitimate shipping costs up to ~$85
                                if value_float > 100 and h_dist < 30:
                                    continue
                            elif value_float > 25 and h_dist < 60:
                                # Standard filter for other vendors: >$25 and <60px
                                continue
                            # 3. Large amounts ($100-$400) with short-medium distance (60-300px) are likely totals/subtotals  
                            # Exception: very far distances (>400px) might be legitimate shipping costs
                            # Relaxed for Liberty Mountain to allow legitimate shipping costs like $185.73
                            elif vendor_name not in ["Liberty Mountain Sports", "Yeti Coolers"] and 100 < value_float <= 400 and 60 <= h_dist <= 300:
                                continue
                            # 4. Medium amounts ($25-$100) with medium distance (80-120px) are likely subtotals
                            # Narrowed range to avoid catching legitimate shipping costs
                            # Disabled for Liberty Mountain and Yeti to allow legitimate shipping costs
                            elif vendor_name not in ["Liberty Mountain Sports", "Yeti Coolers"] and 25 < value_float <= 100 and 80 <= h_dist <= 120:
                                continue
                            # 5. Medium amounts ($25-$100) with large distance (150-250px) are likely totals/subtotals
                            # Disabled for Liberty Mountain and Yeti to allow legitimate shipping costs
                            elif vendor_name not in ["Liberty Mountain Sports", "Yeti Coolers"] and 25 < value_float <= 100 and 150 <= h_dist <= 250:
                                continue
                                
                        except ValueError:
                            pass
                        return extracted_value
        
        # No results found
        return None
    
    # Try primary threshold (60%) first
    primary_labels = find_shipping_labels_in_zone(primary_threshold)
    result = search_for_shipping_values(primary_labels)
    if result:
        # For Liberty Mountain, check for freight allowance deduction
        if vendor_name == "Liberty Mountain Sports":
            try:
                base_shipping = float(result)
                freight_allowance = _extract_liberty_mountain_freight_allowance(words, vendor_name)
                if freight_allowance > 0:
                    net_shipping = base_shipping - freight_allowance
                    # Ensure we don't go negative
                    net_shipping = max(0.0, net_shipping)
                    return f"{net_shipping:.2f}"
            except (ValueError, TypeError):
                pass  # Fall back to original result if calculation fails
        return result
        
    # Fallback to secondary threshold (40%) if primary found nothing
    fallback_labels = find_shipping_labels_in_zone(fallback_threshold)
    result = search_for_shipping_values(fallback_labels)
    if result:
        # For Liberty Mountain, check for freight allowance deduction
        if vendor_name == "Liberty Mountain Sports":
            try:
                base_shipping = float(result)
                freight_allowance = _extract_liberty_mountain_freight_allowance(words, vendor_name)
                if freight_allowance > 0:
                    net_shipping = base_shipping - freight_allowance
                    # Ensure we don't go negative
                    net_shipping = max(0.0, net_shipping)
                    return f"{net_shipping:.2f}"
            except (ValueError, TypeError):
                pass  # Fall back to original result if calculation fails
        return result
    
    # If no shipping cost found in either zone, default to 0.00
    return "0.00"

def _extract_liberty_mountain_freight_allowance(words, vendor_name):
    """
    Extract 'Deduct Freight Allowance' amounts for Liberty Mountain Sports.
    They sometimes have lines like 'Deduct Freight Allowance of $xx.xx'
    """
    if vendor_name != "Liberty Mountain Sports":
        return 0.0
    
    # Look for "Deduct Freight Allowance" or similar patterns
    allowance_patterns = [
        r'deduct\s+freight\s+allowance[^$]*\$\s*([\d,]+\.?\d{0,2})',  # "DEDUCT FREIGHT ALLOWANCE* OF $ 62.52"
        r'freight\s+allowance[^$]*\$\s*([\d,]+\.?\d{0,2})',          # "FREIGHT ALLOWANCE* OF $ 62.52"
        r'deduct.*freight.*\$\s*([\d,]+\.?\d{0,2})',                 # General "DEDUCT...FREIGHT...$ 62.52"
    ]
    
    # Search through all words to build text context
    full_text = ' '.join([word.get('text', '') for word in words]).lower()
    
    for pattern in allowance_patterns:
        import re
        matches = re.findall(pattern, full_text)
        if matches:
            try:
                # Return the first match found
                allowance_amount = float(matches[0].replace(',', ''))
                return allowance_amount
            except (ValueError, IndexError):
                continue
    
    return 0.0

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
        return 0.0 <= value <= 9999.99
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