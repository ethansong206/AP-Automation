# Bugs to fix:
# 1. The code does not handle invoice dates well in multiple-unique-dates cases. (re: Dapper Ink, Yakima)

import re
from datetime import datetime, timedelta
from .utils import try_parse_date

def extract_invoice_date(words, vendor_name):
    text_blob = " ".join([w["text"] for w in words])

    MONTH_NAMES = [
        "Jan(?:uary)?", "Feb(?:ruary)?", "Mar(?:ch)?", "Apr(?:il)?", "May", "Jun(?:e)?",
        "Jul(?:y)?", "Aug(?:ust)?", "Sep(?:t(?:ember)?)?", "Oct(?:ober)?",
        "Nov(?:ember)?", "Dec(?:ember)?"
    ]

    patterns = [
        r"\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12][0-9]|3[01])[/-](?:\d{2}|\d{4})\b",
        r"\b\d{4}[-](?:0?[1-9]|1[0-2])[-](?:0?[1-9]|3[01])\b",
        r"\b(?:{month})\s*\d{{1,2}},?\s*\d{{2,4}}\b".format(month="|".join(MONTH_NAMES)),
        r"\b\d{{1,2}}\s+(?:{month}),?\s+\d{{2,4}}\b".format(month="|".join(MONTH_NAMES)),
        r"\b(?:0?[1-9]|[12][0-9]|3[01])\s+(?:{month})\s+\d{{2,4}}\b".format(month="|".join(MONTH_NAMES)),
        r"\b(?:0?[1-9]|[12][0-9]|3[01])[-](?:{month})[-](?:\d{{2}}|\d{{4}})\b".format(month="|".join(MONTH_NAMES))
    ]
    combined_pattern = "|".join(patterns)

    # DEBUG: Print all words to see how they're split
    print("\n[DEBUG] All words:")
    for i, w in enumerate(words):
        print(f"Word {i}: '{w['text']}'")
    
    # Add a search on the combined text blob
    print("\n[DEBUG] Searching in combined text blob")
    text_blob_matches = re.finditer(combined_pattern, text_blob, flags=re.IGNORECASE)
    blob_matches_found = False
    
    for match in text_blob_matches:
        blob_matches_found = True
        print(f"[DEBUG] Found date in text blob: '{match.group(0)}'")
    
    if not blob_matches_found:
        print("[DEBUG] No dates found in text blob either")

    # Find date strings with positions - NOW USING BLOB MATCHES
    date_candidates = []

    # First, try finding dates in individual words (as before)
    for w in words:
        match = re.search(combined_pattern, w["text"], flags=re.IGNORECASE)
        if match:
            date_candidates.append({
                "text": match.group(0),
                "x": w["x0"],
                "y": w["top"],
                "word": w
            })

    # ALWAYS process blob matches, not just when date_candidates is empty
    if blob_matches_found:
        print("[DEBUG] Processing text blob matches...")
        text_blob_matches = re.finditer(combined_pattern, text_blob, flags=re.IGNORECASE)
        
        for match in text_blob_matches:
            match_text = match.group(0)
            # Skip matches we already found in individual words
            if any(dc["text"] == match_text for dc in date_candidates):
                print(f"[DEBUG] Skipping duplicate blob match: '{match_text}'")
                continue
                
            # Find words near where this match should be in the text
            match_start_pos = match.start()
            match_end_pos = match.end()
            
            # Find the word closest to this match by estimating position in text
            char_count = 0
            closest_word = words[0]
            min_distance = float('inf')
            
            for w in words:
                word_length = len(w["text"])
                word_mid_point = char_count + word_length / 2
                distance_to_match = abs(word_mid_point - (match_start_pos + match_end_pos) / 2)
                
                if distance_to_match < min_distance:
                    min_distance = distance_to_match
                    closest_word = w
                
                char_count += word_length + 1  # +1 for space
            
            date_candidates.append({
                "text": match_text,
                "x": closest_word["x0"],
                "y": closest_word["top"],
                "word": closest_word
            })
            print(f"[DEBUG] Added blob match '{match_text}' using position of word '{closest_word['text']}'")

    print("\n[DEBUG] Regex date matches found:")
    for dc in date_candidates:
        print(f" - {dc['text']} at position ({dc['x']}, {dc['y']})")

    # Parse and validate dates (allowing 8 months in the past)
    today = datetime.today().date()
    MIN_VALID_DATE = (today - timedelta(days=240)).replace(day=1)
    valid_dates = []
    
    for candidate in date_candidates:
        raw_text = candidate["text"].strip().replace(",", "")
        parsed_date = try_parse_date(raw_text)
        
        if parsed_date:
            if MIN_VALID_DATE <= parsed_date <= today:
                valid_dates.append({
                    "date": parsed_date,
                    "x": candidate["x"],
                    "y": candidate["y"],
                    "word": candidate["word"]
                })
                print(f"   ✓ Accepted valid date: {parsed_date} at position ({candidate['x']}, {candidate['y']})")
            else:
                print(f"   ✗ Skipped date {parsed_date}, out of range")
        else:
            print(f"   ✗ Could not parse: {raw_text}")
    
    if not valid_dates:
        print("[DEBUG] No valid dates found.")
        return ""
    
    # Find invoice date labels - SIMPLIFIED APPROACH
    labels = []
    excluded_terms = ["DUE", "SHIPPING", "ORDERED", "SHIP", "ORDER", "PAYMENT", "DISCOUNT"]
    
    # FIRST PRIORITY: Look for exact "INVOICE DATE" phrases
    for i, w in enumerate(words):
        text = w["text"].upper().replace(":", "").strip()
        if "INVOICE DATE" in text or "INV DATE" in text or "INV. DATE" in text:
            # Found an explicit invoice date label - this gets highest priority
            print(f"[DEBUG] Found explicit 'INVOICE DATE' label at ({w['x0']}, {w['top']})")
            
            # Find closest date to this label
            best_date = find_closest_date(valid_dates, w["x0"], w["top"])
            if best_date:
                print(f"[DEBUG] Selected date {best_date} based on proximity to explicit 'INVOICE DATE'")
                return best_date.strftime("%m/%d/%y")
            else:
                print(f"[DEBUG] No valid date found near 'INVOICE DATE' label at ({w['x0']}, {w['top']})")

    # SECOND PRIORITY: Collect ALL standalone "DATE" labels and use the top-most one
    date_labels = []
    for i, w in enumerate(words):
        text = w["text"].upper().replace(":", "").strip()
        if text == "DATE" or text == "DT":
            print(f"[DEBUG] Found potential 'DATE' label at ({w['x0']}, {w['top']})")
            # Check if any excluded terms are nearby - ONLY CHECK BEFORE, not after
            is_excluded = False
            
            for j in range(max(0, i-2), i):  # Only check words BEFORE
                if abs(words[j]["top"] - w["top"]) < 15:
                    nearby_text = words[j]["text"].upper()
                    print(f"[DEBUG] Checking nearby word BEFORE: '{nearby_text}', y-diff: {abs(words[j]['top'] - w['top'])}")
                    if any(term in nearby_text for term in excluded_terms):
                        is_excluded = True
                        print(f"[DEBUG] 'DATE' label excluded due to nearby term '{nearby_text}' containing excluded term")
                        break
                    
                    # Special case: if the word right before is "INVOICE", this is an invoice date!
                    if j == i-1 and ("INVOICE" in nearby_text or "INV" in nearby_text):
                        print(f"[DEBUG] Found 'INVOICE' right before 'DATE' - this is an invoice date!")
                        best_date = find_closest_date(valid_dates, words[j]["x0"], words[j]["top"])
                        if best_date:
                            print(f"[DEBUG] Selected date {best_date} based on 'INVOICE DATE' combination")
                            return best_date.strftime("%m/%d/%y")
        
            if not is_excluded:
                print(f"[DEBUG] Adding valid standalone 'DATE' label at ({w['x0']}, {w['top']})")
                date_labels.append({
                    "x": w["x0"],
                    "y": w["top"],
                    "word": w
                })

    # If we have standalone DATE labels, use the top-most one
    if date_labels:
        # Sort by y-coordinate (top to bottom)
        date_labels.sort(key=lambda x: x["y"])
        top_label = date_labels[0]
        print(f"[DEBUG] Using top-most 'DATE' label at ({top_label['x']}, {top_label['y']})")
        
        best_date = find_closest_date(valid_dates, top_label["x"], top_label["y"])
        if best_date:
            print(f"[DEBUG] Selected date {best_date} based on proximity to top-most 'DATE' label")
            return best_date.strftime("%m/%d/%y")
        else:
            print(f"[DEBUG] No valid date found near top-most 'DATE' label at ({top_label['x']}, {top_label['y']})")
    
    # FALLBACK: Use top-most date
    if valid_dates:
        valid_dates.sort(key=lambda x: x["y"])
        print(f"[DEBUG] No suitable labels found. Using top-most date: {valid_dates[0]['date']}")
        return valid_dates[0]["date"].strftime("%m/%d/%y")
    
    return ""

def find_closest_date(dates, label_x, label_y):
    """Find the date closest to a label position"""
    if not dates:
        print(f"[DEBUG] No valid dates to choose from")
        return None
        
    best_distance = float('inf')
    best_date = None
    
    print(f"[DEBUG] Finding closest date to label at ({label_x}, {label_y})")
    for date_info in dates:
        y_diff = abs(date_info["y"] - label_y)
        x_diff = date_info["x"] - label_x
        
        print(f"[DEBUG] Candidate: {date_info['date']} at ({date_info['x']}, {date_info['y']})")
        print(f"[DEBUG]   - Y-diff: {y_diff}, X-diff: {x_diff}")
        
        # Strongly prefer dates on the same line
        if y_diff < 15:  # Same line
            print(f"[DEBUG]   - On same line (y-diff < 15)")
            
            # Prefer dates to the right of label
            if abs(x_diff) <= 150:  # Date is within a reasonable horizontal distance
                distance = (y_diff * 10) + abs(x_diff)
                print(f"[DEBUG]   - Date is to the RIGHT of label (preferred)")
            else:  # Date is to left (less preferred)
                distance = (y_diff * 10) + abs(x_diff) + 1000  # Penalty
                print(f"[DEBUG]   - Date is to the LEFT of label (+1000 penalty)")
        else:
            # Different lines
            distance = (y_diff * 20) + abs(x_diff)
            print(f"[DEBUG]   - On different line (y-diff >= 15)")
        
        print(f"[DEBUG]   - Final distance score: {distance}")
        
        if distance < best_distance:
            best_distance = distance
            best_date = date_info["date"]
            print(f"[DEBUG]   - New best date! {best_date} with distance {best_distance}")
    
    # Check if the best distance is too high (poor match)
    if best_distance > 500:
        print(f"[DEBUG] Best distance score ({best_distance}) is too high (>500), using fallback to top-most date")
        return None
    
    return best_date