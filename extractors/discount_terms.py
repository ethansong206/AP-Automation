import re
from logging_config import get_logger

logger = get_logger(__name__)

def extract_discount_terms(words, vendor_name):
    all_text = " ".join([w["text"] for w in words]).upper()

    # Tite Line-specific: Check for "2% / 15 net 30" format
    if vendor_name == "Tite Line Fishing Products LLC":
        titeline_pattern = r'(\d{1,2})%\s*/\s*(\d{1,3})\s*NET\s*(\d{1,3})'
        titeline_match = re.search(titeline_pattern, all_text)
        if titeline_match:
            discount_percent = titeline_match.group(1)
            discount_days = titeline_match.group(2)
            net_days = titeline_match.group(3)
            result = f"{discount_percent}% {discount_days} NET {net_days}"
            logger.debug(f"Found Tite Line discount terms: {result}")
            return result

    # Sherpa-specific: Handle "60 DAYS" format
    if vendor_name == "Sherpa":
        sherpa_pattern = r'\b(\d{1,3})\s+DAYS\b'
        sherpa_match = re.search(sherpa_pattern, all_text)
        if sherpa_match:
            days = sherpa_match.group(1)
            result = f"NET {days}"
            logger.debug(f"Found Sherpa discount terms: {result}")
            return result

    # Blundstone-specific: Handle "3% DISCOUNT, 45 DAYS" format
    if vendor_name == "Blundstone":
        blundstone_pattern = r'(\d{1,2})%\s*DISCOUNT,?\s*(\d{1,3})\s*DAYS'
        blundstone_match = re.search(blundstone_pattern, all_text)
        if blundstone_match:
            discount_percent = blundstone_match.group(1)
            days = blundstone_match.group(2)
            result = f"{discount_percent}% {days}"
            logger.debug(f"Found Blundstone discount terms: {result}")
            return result

    # Patagonia and Soto-specific: Calculate NET terms from Due Date - Invoice Date
    if vendor_name in ["Patagonia", "Soto"]:
        from .invoice_date import extract_invoice_date
        from datetime import datetime

        # Look for "Due date" label and extract the date
        due_date_pattern = r'DUE\s+DATE\s*:?\s*(\d{1,2}/\d{1,2}/\d{4})'
        due_date_match = re.search(due_date_pattern, all_text)

        if due_date_match:
            due_date_str = due_date_match.group(1)  # e.g., "1/10/2026"

            # Get invoice date
            invoice_date_str = extract_invoice_date(words, vendor_name)
            if invoice_date_str:
                try:
                    # Parse invoice date (format: MM/DD/YY)
                    invoice_date = datetime.strptime(invoice_date_str, "%m/%d/%y")

                    # Parse due date (format: M/D/YYYY or MM/DD/YYYY)
                    due_date = datetime.strptime(due_date_str, "%m/%d/%Y")

                    # Calculate days difference
                    net_days = (due_date - invoice_date).days

                    result = f"NET {net_days}"
                    logger.debug(f"Found Patagonia calculated terms: {result}")
                    return result
                except Exception as e:
                    logger.error(f"Failed to calculate Patagonia terms from due date: {e}")
                    # Fall through to default NET 60

    # Seirus-specific: Check for date-based terms format: "2% 12/10 Net 12/11"
    if vendor_name == "Seirus Innovation":
        date_terms_pattern = r'(\d{1,2})%\s*(\d{1,2}/\d{1,2})\s*NET\s*(\d{1,2}/\d{1,2})'
        date_terms_match = re.search(date_terms_pattern, all_text)
        if date_terms_match:
            from .invoice_date import extract_invoice_date
            from datetime import datetime

            discount_percent = date_terms_match.group(1)
            discount_date_str = date_terms_match.group(2)  # e.g., "12/10"
            net_date_str = date_terms_match.group(3)  # e.g., "12/11"

            # Get invoice date
            invoice_date_str = extract_invoice_date(words, vendor_name)
            if invoice_date_str:
                try:
                    # Parse invoice date (format: MM/DD/YY)
                    invoice_date = datetime.strptime(invoice_date_str, "%m/%d/%y")

                    # Parse discount and net dates (format: M/D or MM/DD)
                    # Assume same year as invoice, or next year if month has passed
                    discount_month, discount_day = map(int, discount_date_str.split('/'))
                    net_month, net_day = map(int, net_date_str.split('/'))

                    # Create dates with invoice year
                    discount_date = datetime(invoice_date.year, discount_month, discount_day)
                    net_date = datetime(invoice_date.year, net_month, net_day)

                    # If discount date is before invoice date, assume next year
                    if discount_date < invoice_date:
                        discount_date = datetime(invoice_date.year + 1, discount_month, discount_day)
                        net_date = datetime(invoice_date.year + 1, net_month, net_day)

                    # Calculate days difference
                    discount_days = (discount_date - invoice_date).days
                    net_days = (net_date - invoice_date).days

                    result = f"{discount_percent}% {discount_days} NET {net_days}"
                    logger.debug(f"Found date-based discount terms: {result}")
                    return result
                except Exception as e:
                    logger.error(f"Failed to parse date-based discount terms: {e}")
                    # Fall through to regular patterns
    
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
            # Skip "STATEMENT" if it's part of "NO STATEMENT"
            if term == "STATEMENT" and "NO STATEMENT" in first_n_words:
                continue
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

    # Artilect-specific: "60 DAYS PAYMENT TERMS" -> "NET 60"
    if vendor_name == "Artilect":
        match = re.search(r"(\d{1,3})\s*DAYS\s*PAYMENT\s*TERMS", all_text)
        if match:
            result = f"NET {match.group(1)}"
            logger.debug(f"Found Artilect discount terms: {result}")
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

    # Camp USA-specific format: "8% 60/Net 61" -> "8% 60 NET 61"
    if vendor_name == "Camp USA":
        # Look for pattern like "x% yy/Net zz" (case insensitive)
        camp_usa_pattern = r"(\d{1,2})%\s*(\d{1,3})/NET\s*(\d{1,3})"
        match = re.search(camp_usa_pattern, all_text)
        if match:
            result = f"{match.group(1)}% {match.group(2)} NET {match.group(3)}"
            logger.debug(f"Found Camp USA discount terms: {result}")
            return result

    # Hestra-specific format: "8%N90" -> "8% NET 90" or "N90" -> "NET 90"
    if vendor_name == "Hestra Gloves, LLC":
        # Look for pattern like "xx%Nyyy" (with percentage: 1-2 digit %, 1-3 digit days)
        hestra_pattern_with_percent = r"(\d{1,2})%[nN](\d{1,3})\b"
        match = re.search(hestra_pattern_with_percent, all_text)
        if match:
            result = f"{match.group(1)}% NET {match.group(2)}"
            logger.debug(f"Found Hestra discount terms: {result}")
            return result

        # Look for pattern like "Nyyy" (without percentage: 1-3 digit days)
        hestra_pattern_no_percent = r"\b[nN](\d{1,3})\b"
        match = re.search(hestra_pattern_no_percent, all_text)
        if match:
            result = f"NET {match.group(1)}"
            logger.debug(f"Found Hestra discount terms: {result}")
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
        r"\b\d{1,2}%\s*\d{1,3},?\s*[nN]\d{1,3}\b",      # x% xx, nxxx or xx% xxx nxxx (lowercase n variant)
        r"\b\d{1,2}%\s*[nN]\d{1,3}\b",                  # x%Nxx or x% nxx (e.g., 8%N45)
        r"\b\d{1,2}%\s*NET\s*\d{1,3}\b",                # x% NET xx or xx% NET xx
        r"\b\d{1,2}%\s*\d{1,2},?\s*NET\s*\d{1,3}\b",    # x% xx NET xx or xx% xx NET xx
        r"\bNET\s*\d{1,3}\b",                           # NET xx or NET xxx
        r"\bNET\s+DUE\s+IN\s+(\d{1,3})\b",              # NET DUE IN xx
        r"\b\d{1,2}%\s*\d{1,2}\s*NET EOFM\b",           # x% xx NET EOFM or xx% xx NET EOFM (Fulling Mill)
        r"\b\d{4}NET\d{2,3}\b",                         # xxxxNETxx or xxxxNETxxx (10% 60 NET 61 = 1060NET61)
        r"\b\d{3}NET\d{2}\b"                            # xxxNETxx (single digit % like 1% 60 NET 61 = 160NET61)
    ]

    for pattern in patterns:
        match = re.search(pattern, all_text)
        if match:
            value = match.group()

            # Skip if this is part of a product description (e.g., "MOSQUITO NET")
            match_start = match.start()
            match_end = match.end()
            context_start = max(0, match_start - 20)
            context_end = min(len(all_text), match_end + 20)
            context = all_text[context_start:context_end]
            if "MOSQUITO" in context:
                continue
            # Liberty Mountain Sports: insert % and spaces for no-space format
            if vendor_name == "Liberty Mountain Sports":
                # Handle 4-digit format: 1060NET61 -> 10% 60 NET 61
                if re.match(r"\b\d{4}NET\d{2,3}\b", value):
                    digits = re.match(r"(\d{2})(\d{2})NET(\d{2,3})", value)
                    if digits:
                        value = f"{digits.group(1)}% {digits.group(2)} NET {digits.group(3)}"
                # Handle 3-digit format: 160NET61 -> 1% 60 NET 61
                elif re.match(r"\b\d{3}NET\d{2}\b", value):
                    digits = re.match(r"(\d)(\d{2})NET(\d{2})", value)
                    if digits:
                        value = f"{digits.group(1)}% {digits.group(2)} NET {digits.group(3)}"
            # Normalize lowercase 'n' to uppercase 'NET' (e.g., "9% 90, n105" -> "9% 90, NET105")
            value = re.sub(r'\b([nN])(\d)', r'NET\2', value)
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

    # Chaos Headwear, Nocqua, and K'Lani default: if no terms found, default to DUE TODAY
    if vendor_name in ["Chaos Headwear", "Nocqua", "K'Lani LLC"]:
        return "DUE TODAY"

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