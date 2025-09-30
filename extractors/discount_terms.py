import re
from logging_config import get_logger

logger = get_logger(__name__)

def extract_discount_terms(words, vendor_name):
    all_text = " ".join([w["text"] for w in words]).upper()
    
    # Check for special word groups in the first 100 words only
    all_text_words = all_text.split()
    if vendor_name == "Cotopaxi":
        first_n_words = " ".join(all_text_words[:25])
    else:
        first_n_words = " ".join(all_text_words[:100])

    special_terms = [
        "STATEMENT",
        "CREDIT MEMO",
        "CREDIT NOTE",
        "WARRANTY",
        "RETURN AUTHORIZATION",
        "DEFECTIVE",
        "NO TERMS",
        "PRODUCT RETURN",
        "PARTS MISSING",
        "RA FOR CREDIT"
    ]
    for term in special_terms:
        if term in first_n_words:
            logger.debug(f"Found Discount Terms: {term}")
            return term

    # Special cases of terms
    # 1. "90 DAYS NET" -> "NET 90"
    match = re.search(r"\b(\d{1,3})\s+DAYS\s+NET\b", all_text)
    if match:
        result = f"NET {match.group(1)}"
        logger.debug(f"Found Discount Terms: {result}")
        return result

    # 2. "NET TERMS 30" -> "NET 30"
    match = re.search(r"\bNET\s+TERMS\s+(\d{1,3})\b", all_text)
    if match:
        result = f"NET {match.group(1)}"
        logger.debug(f"Found Discount Terms: {result}")
        return result

    # 3. "30 DAYS STRIPE" -> "NET 30"
    match = re.search(r"\b(\d{1,3})\s+DAYS\s+STRIPE\b", all_text)
    if match:
        result = f"NET {match.group(1)}"
        logger.debug(f"Found Discount Terms: {result}")
        return result

    # 4. "NET 120, 75 10%" -> "10% 75 NET 120"
    match = re.search(r"NET\s*(\d{1,3}),?\s*(\d{1,3})\s*(\d{1,2})%\s*", all_text)
    if match:
        # percent, second number, net days
        percent = match.group(3)
        second = match.group(2)
        net_days = match.group(1)
        result = f"{percent}% {second} NET {net_days}"
        logger.debug(f"Found Discount Terms: {result}")
        return result

    # 5. "NET xxD" -> "NET xx" (Grundens and similar cases)
    match = re.search(r"NET\s*(\d{1,2})\s*D\b", all_text)
    if match:
        result = f"NET {match.group(1)}"
        logger.debug(f"Found Discount Terms: {result}")
        return result
    
    # 6. "PAYMENT 90 DAYS" -> "NET 90"
    match = re.search(r"PAYMENT\s*(\d{1,3})\s*DAYS", all_text)
    if match:
        result = f"NET {match.group(1)}"
        logger.debug(f"Found Discount Terms: {result}")
        return result
    
    # 7. "x/x/NET xx or x/xx/NET xx" -> "x% xx NET xx" (National Geographic Maps)
    match = re.search(r"\b(\d{1,2})\s*\/\s*(\d{1,3})\s*\/\s*NET\s*(\d{1,3})\b", all_text)
    if match:
        result = f"{match.group(1)}% {match.group(2)} NET {match.group(3)}"
        logger.debug(f"Found Discount Terms: {result}")
        return result
    
    if vendor_name == "Badfish":
        return "NET 30"  # Special case for Badfish
    
    if vendor_name == "Patagonia":
        return "NET 60"  # Special case for Patagonia
    
    if vendor_name == "Dapper Ink LLC":
        return "DUE TODAY"

    # Rumpl-specific format: Look for "Memo" label with percentage at same Y-coordinate
    if vendor_name == "Rumpl":
        memo_percentage = _extract_rumpl_memo_percentage(words)
        if memo_percentage:
            return memo_percentage

    # Fishpond-specific format: "10% 30, 4% 60, NET 61" -> "10% 30 NET 61"
    if vendor_name == "Fishpond":
        # Look for pattern like "10% 30, 4% 60, NET 61"
        fishpond_pattern = r"(\d{1,2})%\s*(\d{1,3}),\s*\d{1,2}%\s*\d{1,3},\s*NET\s*(\d{1,3})"
        match = re.search(fishpond_pattern, all_text)
        if match:
            result = f"{match.group(1)}% {match.group(2)} NET {match.group(3)}"
            logger.debug(f"Found Discount Terms: {result}")
            return result
    
    # Oboz-specific format: "4%NET 30" -> "4% NET 30"
    if vendor_name == "Oboz Footwear LLC":
        # Look for pattern like "x%NET xx"
        oboz_pattern = r"(\d{1,2})%NET\s*(\d{1,3})"
        match = re.search(oboz_pattern, all_text)
        if match:
            result = f"{match.group(1)}% NET {match.group(2)}"
            logger.debug(f"Found Discount Terms: {result}")
            return result
    
    # Sea to Summit-specific format: "8% 60 / NET 61" -> "8% 60 NET 61"
    if vendor_name == "Sea to Summit":
        # Look for pattern like "x% yy / NET zz"
        sea_to_summit_pattern = r"(\d{1,2})%\s*(\d{1,3})\s*/\s*NET\s*(\d{1,3})"
        match = re.search(sea_to_summit_pattern, all_text)
        if match:
            result = f"{match.group(1)}% {match.group(2)} NET {match.group(3)}"
            logger.debug(f"Found Discount Terms: {result}")
            return result

    # BIG Adventures-specific: Add "DISCOUNT OF X%" to terms if no percentage already exists
    if vendor_name == "BIG Adventures, LLC":
        # First get standard discount terms using normal extraction
        standard_result = None
        for pattern in [
            r"\b\d{1,2}%\s*NET\s*\d{1,3}\b",                # x% NET xx
            r"\b\d{1,2}%\s*\d{1,2},?\s*NET\s*\d{1,3}\b",    # x% xx NET xx
            r"\bNET\s*\d{1,3}\b",                           # NET xx
        ]:
            match = re.search(pattern, all_text)
            if match:
                value = match.group()
                value = value.replace(",", " ")
                value = re.sub(r'%(?=\d)', '% ', value)
                value = re.sub(r'(?<=\d)(?=[A-Z])|(?<=[A-Z])(?=\d)', ' ', value)
                value = re.sub(r"\s+", " ", value).strip()
                standard_result = value
                break

        # Look for "DISCOUNT OF X%, $XX.XX" pattern (handle OCR artifacts like CID:XX)
        discount_pattern = r"DISCOUNT\s+OF\s+(\d{1,2})%,\s*(?:\(CID:\d+\))?\s*\$?[\d,]+\.?\d*"
        special_match = re.search(discount_pattern, all_text)

        # If we found terms, check if they already have a percentage
        if standard_result and "%" not in standard_result:
            if special_match:
                discount_percent = special_match.group(1)
                result = f"{discount_percent}% {standard_result}"
                # logger.debug(f" Found BIG Adventures Combined Terms: {result}")
                return result

        # Return standard result if found (with or without percentage)
        if standard_result:
            # logger.debug(f" Found BIG Adventures Standard Terms: {standard_result}")
            return standard_result

    # Existing patterns
    patterns = [
        r"\b\d{1,2}%\s*NET\s*\d{1,3}\b",                # x% NET xx or xx% NET xx
        r"\b\d{1,2}%\s*\d{1,2},?\s*NET\s*\d{1,3}\b",    # x% xx NET xx or xx% xx NET xx
        r"\bNET\s*\d{1,3}\b",                           # NET xx or NET xxx
        r"\bNET\s+DUE\s+IN\s+(\d{1,3})\b",              # NET DUE IN xx
        r"\b\d{1,2}%\s*\d{1,2}\s*NET EOFM\b",           # x% xx NET EOFM or xx% xx NET EOFM (Fulling Mill)
        r"\b\d{3}NET\d{2}\b"                            # xxxNETxx (Liberty Mountain)
    ]

    for pattern in patterns:
        match = re.search(pattern, all_text)
        if match:
            value = match.group()
            # Liberty Mountain Sports: insert % between first and second numbers for xxxNETxx
            if vendor_name == "Liberty Mountain Sports" and re.match(r"\b\d{3}NET\d{2}\b", value):
                digits = re.match(r"(\d)(\d{2})NET(\d{2})", value)
                if digits:
                    value = f"{digits.group(1)}% {digits.group(2)} NET {digits.group(3)}"
            # Remove commas and standardize spaces
            value = value.replace(",", " ")
            # Insert space after % if followed by digit
            value = re.sub(r'%(?=\d)', '% ', value)
            # Insert space between digit and letter boundaries (but not %)
            value = re.sub(r'(?<=\d)(?=[A-Z])|(?<=[A-Z])(?=\d)', ' ', value)
            # Clean up multiple spaces
            value = re.sub(r"\s+", " ", value).strip()
            if "DUE IN" in value:
                net_days = match.group(1)
                result = f"NET {net_days}"
                logger.debug(f"Found Discount Terms: {result}")
                return result
            # logger.debug(f" Found Discount Terms: {value}")
            return value

    # Gear Aid default: if no terms found, default to NET 60
    if vendor_name == "Gear Aid":
        return "NET 60"
    
    # Scout Curated Wears default: if no terms found, default to NET 30
    if vendor_name == "Scout Curated Wears":
        return "NET 30"
    
    # Turtlebox Audio LLC default: if no terms found, default to NET 30
    if vendor_name == "Turtlebox Audio LLC":
        return "NET 30"

    return ""

def _extract_rumpl_memo_percentage(words):
    """Extract percentage value that appears next to 'Memo' label at same Y-coordinate for Rumpl."""
    if not words:
        return None

    # Find "Memo" labels
    memo_positions = []
    for word in words:
        if word["text"].lower() == "memo":
            memo_positions.append({
                "x0": word["x0"],
                "x1": word["x1"],
                "top": word["top"],
                "page_num": word.get("page_num", 0)
            })

    # Find percentages at same Y-coordinate to the right of memo labels
    for memo_pos in memo_positions:
        memo_page = memo_pos.get("page_num", 0)

        for word in words:
            word_page = word.get("page_num", 0)

            # Skip if on different pages
            if memo_page != word_page:
                continue

            # Check if this word contains a percentage
            if "%" in word["text"]:
                # Check if it's at the same Y-coordinate (within 5px) and to the right
                vertical_alignment = abs(word["top"] - memo_pos["top"])
                horizontal_distance = word["x0"] - memo_pos["x1"]

                if (vertical_alignment <= 5 and          # Same Y-coordinate (±5px)
                    0 <= horizontal_distance <= 300):   # To the right within 300px

                    # Extract just the percentage (e.g., "7%" from "7%")
                    percentage_match = re.search(r"(\d{1,2})%", word["text"])
                    if percentage_match:
                        return f"{percentage_match.group(1)}%"

    return None