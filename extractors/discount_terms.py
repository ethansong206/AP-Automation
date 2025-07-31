import re

def extract_discount_terms(words, vendor_name):
    all_text = " ".join([w["text"] for w in words]).upper()

    # Special cases first
    # 1. "90 DAYS NET" -> "NET 90"
    match = re.search(r"\b(\d{1,3})\s+DAYS\s+NET\b", all_text)
    if match:
        result = f"NET {match.group(1)}"
        print(f"[DEBUG] Found Discount Terms: {result}")
        return result

    # 2. "NET TERMS 30" -> "NET 30"
    match = re.search(r"\bNET\s+TERMS\s+(\d{1,3})\b", all_text)
    if match:
        result = f"NET {match.group(1)}"
        print(f"[DEBUG] Found Discount Terms: {result}")
        return result

    # 3. "30 DAYS STRIPE" -> "NET 30"
    match = re.search(r"\b(\d{1,3})\s+DAYS\s+STRIPE\b", all_text)
    if match:
        result = f"NET {match.group(1)}"
        print(f"[DEBUG] Found Discount Terms: {result}")
        return result

    # 4. "NET 120, 75 10%" -> "10% 75 NET 120"
    match = re.search(r"NET\s*(\d{1,3}),?\s*(\d{1,3})\s*(\d{1,2})%\s*", all_text)
    if match:
        # percent, second number, net days
        percent = match.group(3)
        second = match.group(2)
        net_days = match.group(1)
        result = f"{percent}% {second} NET {net_days}"
        print(f"[DEBUG] Found Discount Terms: {result}")
        return result

    # 5. "NET xxD" -> "NET xx" (Grundens and similar cases)
    match = re.search(r"NET\s*(\d{1,2})\s*D\b", all_text)
    if match:
        result = f"NET {match.group(1)}"
        print(f"[DEBUG] Found Discount Terms: {result}")
        return result
    
    # 6. "PAYMENT 90 DAYS" -> "NET 90"
    match = re.search(r"PAYMENT\s*(\d{1,3})\s*DAYS", all_text)
    if match:
        result = f"NET {match.group(1)}"
        print(f"[DEBUG] Found Discount Terms: {result}")
        return result
    
    if vendor_name == "Badfish":
        return "NET 30"  # Special case for Badfish
    
    if vendor_name == "Patagonia":
        return "NET 90"  # Special case for Patagonia
    
    if vendor_name == "Dapper Ink LLC":
        return "DUE TODAY"

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
            # Remove commas and standardize spaces between digit/letter boundaries
            value = value.replace(",", " ")
            value = re.sub(r'(?<=\d)(?=[A-Z])|(?<=[A-Z])(?=\d)', ' ', value)
            value = re.sub(r"\s+", " ", value).strip()
            if "DUE IN" in value:
                net_days = match.group(1)
                result = f"NET {net_days}"
                print(f"[DEBUG] Found Discount Terms: {result}")
                return result
            print(f"[DEBUG] Found Discount Terms: {value}")
            return value

    # Check for special word groups
    special_terms = [
        "STATEMENT",
        "CREDIT MEMO",
        "CREDIT NOTE",
        "WARRANTY",
        "RETURN AUTHORIZATION",
        "DEFECTIVE",
        "NO CHARGE",
        "NO TERMS"
    ]
    for term in special_terms:
        if term in all_text:
            print(f"[DEBUG] Found Discount Terms: {term}")
            return term

    return ""