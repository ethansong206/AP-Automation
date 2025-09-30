import re
from .common_extraction import (
    normalize_words, 
    find_label_positions, 
    find_value_to_right, 
    find_value_below,
    search_for_pattern
)

initials = [
    "REC",
    "JCS",
    "ACQ",
    "LGC",
    "SMW",
]

def is_potential_po_number(text, vendor_name=None):
    """
    Validates if a string is potentially a PO number
    """

    # Check for buyers' initials at end of PO Number
    for initial in initials:
        if text.strip().upper().endswith(initial):
            return True

    # Check for "TBD" (To Be Determined)
    if text.strip().upper() == "TBD":
        return True
    
    # XD- pattern is specific to PO numbers
    if text.strip().upper().startswith("XD-"):
        return True
        
    # Alpha-hyphen-numeric pattern (like EXE-4609 or ARCADE-123098)
    alpha_hyphen_numeric = r"^[a-zA-Z]+-\d+$"
    if re.match(alpha_hyphen_numeric, text.strip()):
        return True
    
    # CTX3/25 format
    ctx_pattern = r"^[a-zA-Z]+\d+\/\d+$"
    if re.match(ctx_pattern, text.strip()):
        return True
    
    # WORD-DIGIT-DIGIT format
    multi_segment_pattern = r"^[a-zA-Z]+-\d+-\d+$"
    if re.match(multi_segment_pattern, text.strip()):
        return True
        
    # DIGIT-WORD-DIGIT format
    digit_word_digit_pattern = r"^(?:\d+-)[a-zA-Z]+\s*-\s*\d+$"
    if re.match(digit_word_digit_pattern, text.strip()):
        return True
        
    # DIGIT-WORD-DIGIT alternate format
    alt_digit_word_digit = r"^\d+\s*-\s*[a-zA-Z]+-(?:\d+)$"
    if re.match(alt_digit_word_digit, text.strip()):
        return True
        
    # 5+ letters followed by numbers
    long_alpha_numeric = r"^[a-zA-Z]{5,}[0-9]+$"
    if re.match(long_alpha_numeric, text.strip()):
        return True
        
    # Short alpha followed by digits and slash (CTX3/25)
    short_alpha_digit_slash = r"^[a-zA-Z]{3,}\d+\/\d+$"
    if re.match(short_alpha_digit_slash, text.strip()):
        return True
        
    # B2-TARGA325-A format
    complex_pattern = r"^[a-zA-Z0-9]+-[a-zA-Z0-9]+-[a-zA-Z]$"
    if re.match(complex_pattern, text.strip()):
        return True
    
    # 701-thread7.7.25
    period_pattern = r"^[0-9]{3}-[a-zA-Z0-9\.]+"
    if re.match(period_pattern, text.strip()):
        return True
        
    # General alphanumeric with hyphens
    general_alphanumeric = r"^[a-zA-Z0-9]+-[a-zA-Z]+\d+[a-zA-Z0-9\-]*$"
    if re.match(general_alphanumeric, text.strip()):
        return True
    
    # Number-dash-text format (like "401 - hallaman")
    num_dash_text_pattern = r"^\d+\s*[\-:]\s*[a-zA-Z]+$"
    if re.match(num_dash_text_pattern, text.strip()):
        return True
    
    # Customer Name format
    name_pattern = r"^[A-Z]{1}[a-z]+\s*[A-Z]{1}[a-z]+(?:\s*[a-zA-Z0-9\.]+)$"
    if re.match(name_pattern, text.strip()):
        # Exclude names containing "Sale" or "Freeman" (case-insensitive)
        if "sale" in text.strip().lower() or "sales" in text.strip().lower() or "freeman" in text.strip().lower():
            return False
        return True
    
    # Pure numeric strings must be at least 5 digits
    if text.strip().isdigit():
        result = len(text.strip()) >= 5
        return result
    
    # Reject date-like patterns (MM/DD/YY or DD/MM/YY format)
    date_pattern = r"^(0?[1-9]|1[0-2])\/(0?[1-9]|[12][0-9]|3[01])\/\d{2,4}$|^(0?[1-9]|[12][0-9]|3[01])\/(0?[1-9]|1[0-2])\/\d{2,4}$"
    if re.match(date_pattern, text.strip()):
        return False
        
    # Also reject MM/DD format without year
    short_date_pattern = r"^(0?[1-9]|1[0-2])\/(0?[1-9]|[12][0-9]|3[01])$|^(0?[1-9]|[12][0-9]|3[01])\/(0?[1-9]|1[0-2])$"
    if re.match(short_date_pattern, text.strip()):
        return False
    
    # Modified general PO number pattern - more restrictive to avoid matching dates
    general_regex = r"^#?([a-zA-Z0-9]+-[a-zA-Z0-9]+[a-zA-Z0-9\-]*|[a-zA-Z]+-[0-9]{2,}[a-zA-Z0-9\-\/]*|[0-9]{3,}[a-zA-Z]+[0-9a-zA-Z\-\/]*|[a-zA-Z]+[0-9]{3,}[a-zA-Z0-9\-\/]*)$"
    
    result = re.match(general_regex, text.strip(), re.IGNORECASE) is not None
    if result:
        # Exclude candidates that start with "#SE" (case-insensitive)
        if text.strip().upper().startswith("#SE"):
            return False
    return result

def extract_po_from_combined_text(text):
    """
    Extract PO number from combined text like PO#BADFISH-425
    """
    
    # Look for patterns like PO#XXXXX or P.O.#XXXXX
    pattern = r"(?:PO#|P\.?O\.?#)([a-zA-Z0-9\-\/]+)"
    match = re.search(pattern, text, re.IGNORECASE)
    if match:
        result = match.group(1)
        return result
    
    return None

def extract_hobie_po_number(normalized_words):
    """
    Special case handler for Hobie Cat Company II, LLC purchase orders
    where the PO label and number are split across multiple lines
    """
    
    # Find "Purchase" on one line and "Order #:" on the line below
    purchase_words = []
    order_hash_words = []
    
    # To track context, store the previous two words
    prev_words = [None, None]  # [prev-prev word, prev word]
    
    for word in normalized_words:
        if word["text"].lower() == "purchase":
            purchase_words.append(word)
        elif word["orig"] == "#":
            # Only include "Order #" pairs that follow a "Purchase" word
            # and are not preceded by "Sales"
            if prev_words[1] and prev_words[1]["text"] == "order":
                if prev_words[0] and prev_words[0]["text"].lower() == "purchase":
                    # This is a "Purchase Order #" sequence
                    order_hash_words.append({
                        "hash_mark": word,
                        "order_word": prev_words[1],
                        "is_purchase_order": True
                    })
                elif prev_words[0] and prev_words[0]["text"].lower() != "sales":
                    # This might be a different kind of order but not sales
                    order_hash_words.append({
                        "hash_mark": word,
                        "order_word": prev_words[1],
                        "is_purchase_order": False
                    })
        
        # Update the sliding window of previous words
        prev_words = [prev_words[1], word]
    
    
    # Filter to only include Purchase Order # sequences
    purchase_order_hash_words = [item for item in order_hash_words if item["is_purchase_order"]]

    # Try to match # that is vertically below Purchase or Order
    for order_hash in purchase_order_hash_words:
        o_word = order_hash["order_word"]
        hash_mark = order_hash["hash_mark"]
    
        # Check if # is below "Purchase" or "Order" and horizontally aligned
        for ref_word in purchase_words + [o_word]:
            vertical_distance = hash_mark["top"] - ref_word["top"]
            horizontal_overlap = min(ref_word["x1"], hash_mark["x1"]) - max(ref_word["x0"], hash_mark["x0"])
    
            if 5 < vertical_distance < 40 and horizontal_overlap > 0:
    
                # Now look for values to the right of both lines
                right_of_label = []
                right_of_hash = []
    
                for word in normalized_words:
                    # Words to the right of the label ("Purchase" or "Order")
                    if (word["x0"] > ref_word["x1"] and 
                        abs(word["top"] - ref_word["top"]) < 10):
                        right_of_label.append(word)
                        
                    # Words to the right of "#"
                    if (word["x0"] > hash_mark["x1"] and 
                        abs(word["top"] - hash_mark["top"]) < 10):
                        right_of_hash.append(word)
    
                # Sort by x position
                right_of_label.sort(key=lambda w: w["x0"])
                right_of_hash.sort(key=lambda w: w["x0"])
    
                # Create a set to track words we've already added to avoid duplicates
                seen_words = set()
    
                # Combine values in top-to-bottom, left-to-right order
                po_parts = []
                for word in right_of_label:
                    if word["orig"] not in seen_words:
                        po_parts.append(word["orig"])
                        seen_words.add(word["orig"])
    
                for word in right_of_hash:
                    if word["orig"] not in seen_words:
                        po_parts.append(word["orig"])
                        seen_words.add(word["orig"])

                if po_parts:
                    po_number = "".join(po_parts).strip()
                    return po_number
    
    return None

def filter_po_box_labels(po_label_positions, normalized_words):
    """
    Remove PO label positions that are actually 'PO Box'
    """
    filtered_positions = []
    for idx, (x0, x1, y) in enumerate(po_label_positions):
        is_po_box = False
        for word in normalized_words:
            if (word["text"] == "box" and 
                word["x0"] > x1 and 
                abs(word["top"] - y) < 10):
                is_po_box = True
                break
        if not is_po_box:
            filtered_positions.append((x0, x1, y))
    return filtered_positions

def extract_po_number(words, vendor_name):
    """
    Extract PO number from document
    """
    
    normalized_words = normalize_words(words)

    # Special case for Nemo and Topo Designs
    if vendor_name:
        vendor_lower = vendor_name.lower()
        if "nemo" in vendor_lower or "topo designs" in vendor_lower:
            po_label_positions = find_label_positions(normalized_words, label_type="po")
            po_label_positions = filter_po_box_labels(po_label_positions, normalized_words)
            if not po_label_positions:
                return ""
            label_x0, label_x1, label_y = po_label_positions[0]
            x0_delta = 10  # px tolerance for x0 alignment
            max_y_dist = 150  # px max vertical distance below label

            candidates = []
            for w in normalized_words:
                vertical_distance = w["top"] - label_y
                if "nemo" in vendor_lower:
                    # Nemo: strict x0 alignment
                    if (
                        abs(w["x0"] - label_x0) <= x0_delta
                        and 5 < vertical_distance <= max_y_dist
                    ):
                        candidates.append(w)
                elif "topo designs" in vendor_lower:
                    # Topo Designs: 5px buffer left, 80px right of label_x0
                    if (
                        (label_x0 - 5 <= w["x0"] <= label_x0 + 80)
                        and 5 < vertical_distance <= max_y_dist
                    ):
                        candidates.append(w)

            # Group by y (line)
            lines = {}
            for w in candidates:
                line_y = round(w["top"])
                if line_y not in lines:
                    lines[line_y] = []
                lines[line_y].append(w)

            # Sort lines by y (top to bottom)
            sorted_line_ys = sorted(lines.keys())
            num_lines = 3 if "nemo" in vendor_lower else 2
            selected_lines = []
            for line_y in sorted_line_ys[:num_lines]:
                # Sort words left-to-right
                line_words = sorted(lines[line_y], key=lambda w: w["x0"])
                selected_lines.append(" ".join(w["orig"] for w in line_words))
            if selected_lines:
                po_number = " ".join(selected_lines).strip()
                return po_number
            return ""

    # Special case for Hobie Cat Company II, LLC
    if vendor_name and "hobie cat company ii" in vendor_name.lower():
        hobie_po = extract_hobie_po_number(normalized_words)
        if hobie_po:
            return hobie_po
        # If special extraction fails, continue with standard methods

    # Special case for Vuori - look for "Customer Reference" label
    if vendor_name and "vuori" in vendor_name.lower():

        # Find "Customer Reference" label (case insensitive, flexible spacing)
        for i in range(len(normalized_words) - 1):
            first_word = normalized_words[i]
            second_word = normalized_words[i + 1]

            if (first_word["text"].lower() == "customer" and
                second_word["text"].lower() == "reference"):

                label_y = first_word["top"]
                label_x_end = second_word["x1"]


                # Look for values directly to the right on the same y-level
                y_tolerance = 5  # pixels
                candidates = []

                for word in normalized_words:
                    # Must be to the right of the label and on same y-level
                    if (word["x0"] > label_x_end and
                        abs(word["top"] - label_y) <= y_tolerance):
                        candidates.append(word)

                if candidates:
                    # Sort by x position (left to right)
                    candidates.sort(key=lambda w: w["x0"])

                    # Try individual words first
                    for candidate in candidates:
                        if is_potential_po_number(candidate["orig"], vendor_name):
                            return candidate["orig"]

                    # Try combining nearby words if individual words don't work
                    for i in range(len(candidates)):
                        for j in range(i + 1, min(i + 3, len(candidates) + 1)):  # Try 2-3 word combinations
                            combined_words = candidates[i:j]

                            # Check if words are reasonably close to each other
                            too_far_apart = False
                            for k in range(len(combined_words) - 1):
                                if combined_words[k+1]["x0"] - combined_words[k]["x1"] > 20:
                                    too_far_apart = True
                                    break

                            if not too_far_apart:
                                combined_text = " ".join(w["orig"] for w in combined_words)
                                if is_potential_po_number(combined_text, vendor_name):
                                        return combined_text

                break  # Only check the first "Customer Reference" found


    # First priority: Look for combined PO# text
    
    for word in normalized_words:
        if "po#" in word["orig"].lower() or "p.o.#" in word["orig"].lower():
            po_number = extract_po_from_combined_text(word["orig"])
            if po_number:
                return po_number
    
    
    # Second priority: Check for explicit patterns directly
    
    patterns = [
        r"^XD-\d+$",  # XD-12345
        r"^099-[0-9a-zA-Z]+",
        r"^999-[0-9a-zA-Z]+",
        r"^99-[0-9a-zA-Z]+"
    ]
    
    for i, pattern in enumerate(patterns):
        
        pattern_match = search_for_pattern(normalized_words, pattern, case_sensitive=False)
        if pattern_match:
            return pattern_match
    
    
    # Third priority: Find PO labels and look to the right
    
    po_label_positions = find_label_positions(normalized_words, label_type="po")
    
    # Yakima uses "Purchaser Order No." instead of standard PO labels
    if vendor_name and "yakima" in vendor_name.lower():
        for i in range(len(normalized_words) - 2):
            first = normalized_words[i]
            second = normalized_words[i + 1]
            third = normalized_words[i + 2]
            if (
                first["text"] == "purchaser"
                and second["text"] == "order"
                and third["text"] in ["no", "no.", "number", "num", "#"]
            ):
                po_label_positions.append((first["x0"], third["x1"], first["top"]))

    
    # Add "P.O. No." labels
    for i in range(len(normalized_words) - 2):
        first = normalized_words[i]
        second = normalized_words[i + 1]
        
        # Be more flexible with P.O. No. detection
        if ((first["text"] in ["po", "p.o", "p.o."]) and 
            (second["text"] in ["no", "no.", "number", "num", "#"])):
            # Combine their bounding boxes for the label position
            po_label_positions.append((first["x0"], second["x1"], first["top"]))
            label_text = f"{first['orig']} {second['orig']}"
    
    # Add "Customer PO" labels
    for i in range(len(normalized_words) - 1):
        first = normalized_words[i]
        second = normalized_words[i + 1]
        
        if (first["text"].lower() == "customer" and 
            (second["text"].lower() in ["po", "p.o", "p.o.", "purchase", "order"])):
            # Combine their bounding boxes for the label position
            po_label_positions.append((first["x0"], second["x1"], first["top"]))
        
        # Also check for "Customer PO:" or "Customer PO#" as a combined term
        if (first["text"].lower().startswith("customer") and 
            ("po" in first["text"].lower() or "p.o" in first["text"].lower() or 
             "purchase order" in first["text"].lower())):
            po_label_positions.append((first["x0"], first["x1"], first["top"]))
    
    # Add "PO/Ref #" labels
    for i in range(len(normalized_words) - 1):
        first = normalized_words[i]
        second = normalized_words[i + 1]
        
        if ((first["text"] in ["po", "p.o", "p.o."]) and 
            ("ref" in second["text"].lower() or second["text"] == "#")):
            # Combine their bounding boxes for the label position
            po_label_positions.append((first["x0"], second["x1"], first["top"]))
        
        # Also check for "PO/Ref" without the "#" as a single word
        if "po/ref" in first["text"].lower() or "p.o./ref" in first["text"].lower():
            po_label_positions.append((first["x0"], first["x1"], first["top"]))
    
    # Filter out "PO Box" cases
    po_label_positions = filter_po_box_labels(po_label_positions, normalized_words)

    for idx, (x0, x1, y) in enumerate(po_label_positions):
        # Find the words that make up this label
        label_text = []
        for word in normalized_words:
            if (abs(word["top"] - y) < 5 and 
                word["x0"] >= x0 - 5 and word["x1"] <= x1 + 5):
                label_text.append(word["orig"])
        
        label_str = " ".join(label_text) if label_text else "Unknown"
    
    # Look for value to the right of any PO label
    
    po_right_match = find_value_to_right(normalized_words, po_label_positions, 
                                        lambda text: is_potential_po_number(text, vendor_name),
                                        strict=True)
    if po_right_match:
        return po_right_match
    
    
    # Fourth priority: Look below labels with direct line-based search
    
    max_distance_below = 40  # Keep this modest to avoid false positives
    
    for label_idx, (label_x0, label_x1, label_y) in enumerate(po_label_positions):
        
        # First, collect all words that appear below this label
        words_below = []
        for w in normalized_words:
            mid_x = (w["x0"] + w["x1"]) / 2
            vertical_distance = w["top"] - label_y
            
            # Check if word is centered below label with reasonable distance
            if (label_x0 - 30 <= mid_x <= label_x1 + 30 and
                5 < vertical_distance <= max_distance_below):
                words_below.append((w, vertical_distance))
        
        # Group words by line (similar y-position)
        lines = {}
        for w, distance in words_below:
            line_y = round(w["top"])  # Round to nearest pixel for grouping
            if line_y not in lines:
                lines[line_y] = []
            lines[line_y].append(w)
        
        # Process each line
        for line_y, line_words in lines.items():
            # Sort words by x-position
            line_words.sort(key=lambda w: w["x0"])
            
            # First, try the ENTIRE line as a single PO if it's a reasonable length (2-5 words)
            if 2 <= len(line_words) <= 5:
                # Reconstruct the full line with spaces
                full_line = " ".join(word["orig"] for word in line_words)
                if is_potential_po_number(full_line, vendor_name):
                    return full_line
                
                # Also try without spaces
                full_line_no_spaces = "".join(word["orig"] for word in line_words)
                if is_potential_po_number(full_line_no_spaces, vendor_name):
                    return full_line_no_spaces
            
            # Try each individual word
            for w in line_words:
                if is_potential_po_number(w["orig"], vendor_name):
                    return w["orig"]
            
            # Special case: Check for pattern like "401 - hallaman"
            if len(line_words) >= 3:
                for i in range(len(line_words) - 2):
                    # Check for typical number-dash-text pattern
                    if (line_words[i]["orig"].strip().isdigit() and 
                        "-" in line_words[i+1]["orig"] and
                        not line_words[i+2]["orig"].strip().isdigit()):
                        
                        po_candidate = f"{line_words[i]['orig']} {line_words[i+1]['orig']} {line_words[i+2]['orig']}"
                        if is_potential_po_number(po_candidate, vendor_name):
                            return po_candidate
            
            # Try various combinations of adjacent words
            for span in range(2, min(4, len(line_words) + 1)):  # Try spans of 2-3 words
                for i in range(len(line_words) - span + 1):
                    # Check if words are reasonably close to each other
                    word_group = line_words[i:i+span]
                    too_far_apart = False
                    
                    for j in range(len(word_group) - 1):
                        if word_group[j+1]["x0"] - word_group[j]["x1"] > 25:  # Increased from 15px to 25px
                            too_far_apart = True
                            break
                            
                    if not too_far_apart:
                        # Try with spaces
                        combined = " ".join(word["orig"] for word in word_group)
                        if is_potential_po_number(combined, vendor_name):
                            return combined
                        
                        # Try without spaces
                        combined_no_spaces = "".join(word["orig"] for word in word_group)
                        if is_potential_po_number(combined_no_spaces, vendor_name):
                            return combined_no_spaces
    
    return ""
