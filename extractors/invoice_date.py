import re
from datetime import datetime, timedelta
from .utils import try_parse_date
from logging_config import get_logger

logger = get_logger(__name__)

def extract_invoice_date(words, vendor_name):
    # Carve Designs-specific logic: for email format, skip dates with timestamps
    if vendor_name == "Carve Designs":
        from .email_detection import is_email_format
        
        if is_email_format(words):
            # Filter out dates that are followed by timestamps (email dates)
            text_blob = " ".join([w["text"] for w in words])
            
            # Create a list to store dates with timestamps to exclude
            timestamp_dates = []
            
            # Look for dates followed by time patterns
            timestamp_patterns = [
                r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s+\d{1,2}:\d{2}(?::\d{2})?\s*(?:AM|PM)?',  # MM/DD/YY HH:MM or HH:MM AM/PM
                r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s+at\s+\d{1,2}:\d{2}',  # MM/DD/YY at HH:MM
                r'(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\s+\d{1,2}:\d{2}'  # Day MM/DD/YY HH:MM
            ]
            
            for pattern in timestamp_patterns:
                matches = re.finditer(pattern, text_blob, flags=re.IGNORECASE)
                for match in matches:
                    # Extract just the date portion from the timestamp match
                    date_match = re.search(r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}', match.group(0))
                    if date_match:
                        timestamp_dates.append(date_match.group(0))
            
            # Filter out words that are part of timestamp contexts, not just contain timestamp dates
            if timestamp_dates:
                filtered_words = []
                for i, word in enumerate(words):
                    word_text = word["text"]
                    
                    # Check if this word contains a date that was part of a timestamp
                    contains_timestamp_date = any(date in word_text for date in timestamp_dates)
                    
                    if contains_timestamp_date:
                        # Check surrounding context to see if this is really part of a timestamp
                        is_timestamp_context = False
                        
                        # Look at nearby words for time indicators
                        for j in range(max(0, i-3), min(len(words), i+4)):
                            if j == i:
                                continue
                            nearby_text = words[j]["text"].upper()
                            
                            # Check if nearby words indicate this is a timestamp
                            time_indicators = ["AM", "PM", ":", "AT", "MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]
                            if any(indicator in nearby_text for indicator in time_indicators):
                                # Additional check: make sure it's not just ":" from "Invoice Date:"
                                if ":" in nearby_text and ("DATE" in nearby_text or "INVOICE" in nearby_text):
                                    continue  # This is likely "Invoice Date:", not a timestamp
                                is_timestamp_context = True
                                break
                        
                        # Only exclude if it's truly in a timestamp context
                        if not is_timestamp_context:
                            filtered_words.append(word)
                    else:
                        filtered_words.append(word)
                
                # Use filtered words for date extraction
                words = filtered_words
    
    # Arc'teryx-specific logic: handle incomplete "September 10, 202" dates  
    if vendor_name == "Arc'teryx":
        text_blob = " ".join([w["text"] for w in words])
        
        # Look for incomplete September dates that need reconstruction
        sep_pattern = r'September\s+(\d{1,2}),?\s+(?:202|20)(?:\d)?'
        sep_match = re.search(sep_pattern, text_blob, re.IGNORECASE)
        
        if sep_match:
            # Extract the day number
            day = sep_match.group(1)
            
            # Get current year to construct proper date
            current_year = datetime.now().year
            
            # Construct the complete date - Arc'teryx invoices are typically current year
            reconstructed_date = f"09/{day.zfill(2)}/{str(current_year)[-2:]}"
            
            # Validate this reconstructed date is reasonable (within our 480-day range)
            parsed_date = try_parse_date(reconstructed_date)
            
            if parsed_date:
                today = datetime.today().date()
                MIN_VALID_DATE = (today - timedelta(days=480)).replace(day=1)
                
                if MIN_VALID_DATE <= parsed_date <= today:
                    logger.debug(f"Arc'teryx: Reconstructed '{sep_match.group(0)}' as {reconstructed_date}")
                    return reconstructed_date
    
    # Lifestraw-specific logic: use top-most date (consistent format)
    if vendor_name == "Lifestraw":
        # Find all valid dates and use the top-most one
        text_blob = " ".join([w["text"] for w in words])
        
        # Find all dates in the document
        date_candidates = []
        date_pattern = r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
        
        for word in words:
            date_match = re.search(date_pattern, word["text"])
            if date_match:
                date_text = date_match.group(0)
                parsed_date = try_parse_date(date_text)
                if parsed_date:
                    today = datetime.today().date()
                    MIN_VALID_DATE = (today - timedelta(days=480)).replace(day=1)
                    if MIN_VALID_DATE <= parsed_date <= today:
                        date_candidates.append({
                            "date": parsed_date,
                            "y": word["top"],
                            "text": date_text
                        })
        
        if date_candidates:
            # Sort by Y coordinate (top to bottom) and use the top-most
            date_candidates.sort(key=lambda x: x["y"])
            top_date = date_candidates[0]
            logger.debug(f"Lifestraw: Using top-most date '{top_date['text']}'")
            return top_date["date"].strftime("%m/%d/%y")
    
    # Nite Ize Inc-specific logic: use top-most date (consistent format)
    if vendor_name == "Nite Ize Inc":
        # Find all valid dates and use the top-most one
        date_candidates = []
        date_pattern = r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
        
        for word in words:
            date_match = re.search(date_pattern, word["text"])
            if date_match:
                date_text = date_match.group(0)
                parsed_date = try_parse_date(date_text)
                if parsed_date:
                    today = datetime.today().date()
                    MIN_VALID_DATE = (today - timedelta(days=480)).replace(day=1)
                    if MIN_VALID_DATE <= parsed_date <= today:
                        date_candidates.append({
                            "date": parsed_date,
                            "y": word["top"],
                            "text": date_text
                        })
        
        if date_candidates:
            # Sort by Y coordinate (top to bottom) and use the top-most
            date_candidates.sort(key=lambda x: x["y"])
            top_date = date_candidates[0]
            logger.debug(f"Nite Ize Inc: Using top-most date '{top_date['text']}'")
            return top_date["date"].strftime("%m/%d/%y")
    
    # Salomon-specific logic: use left-most date (consistent format)
    if vendor_name == "Salomon":
        # Find all valid dates and use the left-most one
        date_candidates = []
        date_pattern = r'\d{1,2}[/-]\d{1,2}[/-]\d{2,4}'
        
        for word in words:
            date_match = re.search(date_pattern, word["text"])
            if date_match:
                date_text = date_match.group(0)
                parsed_date = try_parse_date(date_text)
                if parsed_date:
                    today = datetime.today().date()
                    MIN_VALID_DATE = (today - timedelta(days=480)).replace(day=1)
                    if MIN_VALID_DATE <= parsed_date <= today:
                        date_candidates.append({
                            "date": parsed_date,
                            "x": word["x0"],
                            "text": date_text
                        })
        
        if date_candidates:
            # Sort by X coordinate (left to right) and use the left-most
            date_candidates.sort(key=lambda x: x["x"])
            left_date = date_candidates[0]
            logger.debug(f"Salomon: Using left-most date '{left_date['text']}'")
            return left_date["date"].strftime("%m/%d/%y")
    
    # Saxx Underwear-specific logic: handle YYYY-MM-DD format
    if vendor_name == "Saxx Underwear":
        # Look for YYYY-MM-DD format and convert to standard format for normal processing
        text_blob = " ".join([w["text"] for w in words])
        
        # Find YYYY-MM-DD dates and add them as converted words
        yyyy_mm_dd_pattern = r'\b(\d{4})-(\d{1,2})-(\d{1,2})\b'
        converted_words = []
        
        for word in words:
            # Check if this word or nearby text contains YYYY-MM-DD format
            word_context = word["text"]
            match = re.search(yyyy_mm_dd_pattern, word_context)
            if match:
                year, month, day = match.groups()
                # Convert to MM/DD/YY format
                converted_date = f"{month.zfill(2)}/{day.zfill(2)}/{year[-2:]}"
                
                # Create a new word with the converted date
                converted_word = word.copy()
                converted_word["text"] = converted_date
                converted_words.append(converted_word)
            else:
                converted_words.append(word)
        
        # Replace words with converted versions for normal processing
        words = converted_words
    
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
    
    # Add a search on the combined text blob
    logger.debug("Searching in combined text blob")
    text_blob_matches = re.finditer(combined_pattern, text_blob, flags=re.IGNORECASE)
    blob_matches_found = False
    
    for match in text_blob_matches:
        blob_matches_found = True
        logger.debug(f"Found date in text blob: '{match.group(0)}'")
    
    #if not blob_matches_found:
        logger.debug("No dates found in text blob either")

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
        logger.debug("Processing text blob matches...")
        text_blob_matches = re.finditer(combined_pattern, text_blob, flags=re.IGNORECASE)
        
        for match in text_blob_matches:
            match_text = match.group(0)
            # Skip matches we already found in individual words
            if any(dc["text"] == match_text for dc in date_candidates):
                #print(f"[DEBUG] Skipping duplicate blob match: '{match_text}'")
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
            #print(f"[DEBUG] Added blob match '{match_text}' using position of word '{closest_word['text']}'")

    logger.debug("Regex date matches found:")
    #for dc in date_candidates:
    #    print(f" - {dc['text']} at position ({dc['x']}, {dc['y']})")

    # Parse and validate dates (allowing 8 months in the past)
    today = datetime.today().date()
    MIN_VALID_DATE = (today - timedelta(days=480)).replace(day=1)
    valid_dates = []
    
    for candidate in date_candidates:
        raw_text = candidate["text"].strip().replace(",", "")
        # Only convert dashes to slashes for numeric dates, not month-name dates
        if re.match(r'^\d{1,2}-\d{1,2}-\d{2,4}$', raw_text):
            raw_text = raw_text.replace("-", "/")
        parsed_date = try_parse_date(raw_text)
        
        if parsed_date:
            logger.debug(f"Parsed date: {parsed_date}, Range check: {MIN_VALID_DATE} <= {parsed_date} <= {today}")
            if MIN_VALID_DATE <= parsed_date <= today:
                valid_dates.append({
                    "date": parsed_date,
                    "x": candidate["x"],
                    "y": candidate["y"],
                    "word": candidate["word"]
                })
                logger.debug(f"OK Accepted valid date: {parsed_date} at position ({candidate['x']}, {candidate['y']})")
            #else:
                logger.debug(f"X Skipped date {parsed_date}, out of range")
        #else:
            logger.debug(f"X Could not parse: {raw_text}")
    
    if not valid_dates:
        logger.debug("No valid dates found.")
        return ""
    
    # Find invoice date labels - SIMPLIFIED APPROACH
    labels = []
    excluded_terms = ["DUE", "SHIPPING", "ORDERED", "SHIP", "ORDER", "PAYMENT", "DISCOUNT"]
    
    # FIRST PRIORITY: Look for exact "INVOICE DATE" or "CREDIT MEMO DATE" phrases
    for i, w in enumerate(words):
        text = w["text"].upper().replace(":", "").strip()
        if "INVOICE DATE" in text or "INV DATE" in text or "INV. DATE" in text or "CREDIT MEMO DATE" in text or "MEMO DATE" in text:
            # Found an explicit invoice date label - this gets highest priority
            #print(f"[DEBUG] Found explicit 'INVOICE DATE' or 'CREDIT MEMO DATE' label at ({w['x0']}, {w['top']})")
            
            # Find closest date to this label
            best_date = find_closest_date(valid_dates, w["x0"], w["top"])
            if best_date:
                #print(f"[DEBUG] Selected date {best_date} based on proximity to explicit 'INVOICE DATE'")
                return best_date.strftime("%m/%d/%y")
            #else:
                #print(f"[DEBUG] No valid date found near 'INVOICE DATE' label at ({w['x0']}, {w['top']})")

    # SECOND PRIORITY: Collect ALL standalone "DATE" labels and use the top-most one
    date_labels = []
    for i, w in enumerate(words):
        text = w["text"].upper().strip()
        clean_text = text.replace(":", "").strip()
        if clean_text == "DATE" or clean_text == "DT":
            #print(f"[DEBUG] Found potential 'DATE' label at ({w['x0']}, {w['top']})")
            # Check if any excluded terms are nearby - ONLY CHECK BEFORE, not after
            is_excluded = False
            
            for j in range(max(0, i-2), i):  # Only check words BEFORE
                if abs(words[j]["top"] - w["top"]) < 15:
                    nearby_text = words[j]["text"].upper()
                    #print(f"[DEBUG] Checking nearby word BEFORE: '{nearby_text}', y-diff: {abs(words[j]['top'] - w['top'])}")
                    if any(term in nearby_text for term in excluded_terms):
                        is_excluded = True
                        #print(f"[DEBUG] 'DATE' label excluded due to nearby term '{nearby_text}' containing excluded term")
                        break
                    
                    # Special case: if the word right before is "INVOICE", this is an invoice date!
                    if j == i-1 and ("INVOICE" in nearby_text or "INV" in nearby_text):
                        #print(f"[DEBUG] Found 'INVOICE' right before 'DATE' - this is an invoice date!")
                        best_date = find_closest_date(valid_dates, words[j]["x0"], words[j]["top"])
                        if best_date:
                            #print(f"[DEBUG] Selected date {best_date} based on 'INVOICE DATE' combination")
                            return best_date.strftime("%m/%d/%y")
        
            if not is_excluded:
                #print(f"[DEBUG] Adding valid standalone 'DATE' label at ({w['x0']}, {w['top']})")
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
        #print(f"[DEBUG] Using top-most 'DATE' label at ({top_label['x']}, {top_label['y']})")
        
        best_date = find_closest_date(valid_dates, top_label["x"], top_label["y"])
        if best_date:
            #print(f"[DEBUG] Selected date {best_date} based on proximity to top-most 'DATE' label")
            return best_date.strftime("%m/%d/%y")
        #else:
            #print(f"[DEBUG] No valid date found near top-most 'DATE' label at ({top_label['x']}, {top_label['y']})")
    
    # FALLBACK: Use top-most date
    if valid_dates:
        valid_dates.sort(key=lambda x: x["y"])
        #print(f"[DEBUG] No suitable labels found. Using top-most date: {valid_dates[0]['date']}")
        return valid_dates[0]["date"].strftime("%m/%d/%y")
    
    return ""

def find_closest_date(dates, label_x, label_y):
    """Find the date closest to a label position"""
    if not dates:
        #print(f"[DEBUG] No valid dates to choose from")
        return None
        
    best_distance = float('inf')
    best_date = None
    
    #print(f"[DEBUG] Finding closest date to label at ({label_x}, {label_y})")
    for date_info in dates:
        y_diff = abs(date_info["y"] - label_y)
        x_diff = date_info["x"] - label_x
        
        #print(f"[DEBUG] Candidate: {date_info['date']} at ({date_info['x']}, {date_info['y']})")
        #print(f"[DEBUG]   - Y-diff: {y_diff}, X-diff: {x_diff}")
        
        # Strongly prefer dates on the same line
        if y_diff < 15:  # Same line
            #print(f"[DEBUG]   - On same line (y-diff < 15)")
            
            # Prefer dates to the right of label
            if abs(x_diff) <= 150:  # Date is within a reasonable horizontal distance
                distance = (y_diff * 10) + abs(x_diff)
                #print(f"[DEBUG]   - Date is to the RIGHT of label (preferred)")
            else:  # Date is to left (less preferred)
                distance = (y_diff * 10) + abs(x_diff) + 1000  # Penalty
                #print(f"[DEBUG]   - Date is to the LEFT of label (+1000 penalty)")
        else:
            # Different lines
            distance = (y_diff * 20) + abs(x_diff)
            #print(f"[DEBUG]   - On different line (y-diff >= 15)")
        
        #print(f"[DEBUG]   - Final distance score: {distance}")
        
        if distance < best_distance:
            best_distance = distance
            best_date = date_info["date"]
            #print(f"[DEBUG]   - New best date! {best_date} with distance {best_distance}")
    
    # Check if the best distance is too high (poor match)
    if best_distance > 500:
        #print(f"[DEBUG] Best distance score ({best_distance}) is too high (>500), using fallback to top-most date")
        return None
    
    return best_date