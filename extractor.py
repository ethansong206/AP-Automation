import re
from datetime import datetime, timedelta

# Define helper patterns
DATE_PATTERN = r"\b(?:\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4}|\d{4}[/\-]\d{1,2}[/\-]\d{1,2})\b"
MONEY_PATTERN = r"\$\s?\d+[,.]?\d*"

def extract_fields(documents):
    extracted_rows = []

    for doc in documents:
        words = doc["words"]
        file_name = doc.get("file_name", "Unknown")

        row = {
            "Vendor Name": extract_vendor(words),
            "Invoice Number": extract_invoice_number(words),
            "Invoice Date": extract_invoice_date(words),
            "Discount Terms": extract_discount_terms(words),
            "Discount Due Date": "",
            "Discounted Total": "",
            "Total Amount": extract_total_amount(words)
        }

        # Calculate Discount Due and Discounted Total
        if row["Discount Terms"] and row["Invoice Date"] and row["Total Amount"]:
            try:
                discounted_due, discounted_total = calculate_discount_fields(
                    row["Discount Terms"], row["Invoice Date"], row["Total Amount"]
                )
                row["Discount Due Date"] = discounted_due
                row["Discounted Total"] = discounted_total
            except Exception as e:
                print(f"[WARN] Could not compute discount fields: {e}")

        extracted_rows.append([
            row["Vendor Name"], row["Invoice Number"], row["Invoice Date"],
            row["Discount Terms"], row["Discount Due Date"],
            row["Discounted Total"], row["Total Amount"]
        ])

    return extracted_rows

# ------------------ Invoice Number Extractor ------------------

def extract_invoice_number(words):
    # Only consider words from page 0 (the first page)
    first_page_words = [w for w in words if w.get("page_num", 0) == 0]

    print(f"[DEBUG] Using page_num == 0 to restrict to first page")
    print(f"[DEBUG] Retained {len(first_page_words)} words for first-page invoice check")

    normalized_words = [
        {
            "index": i,
            "text": w["text"].strip().lower().replace(":", "").replace("#", ""),
            "orig": w["text"],
            "x0": w["x0"],
            "x1": w["x1"],
            "top": w["top"],
            "bottom": w["bottom"]
        }
        for i, w in enumerate(first_page_words)
    ]

    label_positions = []

    for i in range(len(normalized_words) - 1):
        first = normalized_words[i]
        second = normalized_words[i + 1]
        if first["text"] == "invoice" and second["text"] in ["#", "no", "number"]:
            label_positions.append((first["x0"], second["x1"], second["top"]))

    for w in normalized_words:
        if w["text"] == "invoice":
            label_positions.append((w["x0"], w["x1"], w["top"]))

    # Step 1: Directly to the right (±5px vertically)
    for label_x0, label_x1, label_y in label_positions:
        candidates = [
            w for w in normalized_words
            if w["x0"] > label_x1 and abs(w["top"] - label_y) <= 5 and is_potential_invoice_number(w["text"])
        ]
        if candidates:
            best = sorted(candidates, key=lambda x: abs(x["top"] - label_y))[0]
            print(f"[DEBUG] Invoice Number (direct right match): {best['orig']}")
            return best["orig"].lstrip("#:").strip()

    # Step 2: Right and slightly offset vertically (±20px)
    for label_x0, label_x1, label_y in label_positions:
        candidates = [
            w for w in normalized_words
            if w["x0"] > label_x1 and abs(w["top"] - label_y) <= 20 and is_potential_invoice_number(w["text"])
        ]
        if candidates:
            best = sorted(candidates, key=lambda x: abs(x["top"] - label_y))[0]
            label_word = next(
                (w["text"] for w in words if abs(w["x0"] - label_x0) < 2 and abs(w["x1"] - label_x1) < 2 and abs(w["top"] - label_y) < 2),
                f"coords=({label_x0:.1f}, {label_y:.1f})"
            )
            print(f"[DEBUG] Invoice Number (loose right match from label '{label_word}'): {best['orig']}")
            return best["orig"].lstrip("#:").strip()

    # Step 3: Below fallback (limit vertical distance and score best across all labels)
    max_distance_below = 150
    best_candidate = None
    best_score = float("inf")

    for label_idx, (label_x0, label_x1, label_y) in enumerate(label_positions):
        for w in normalized_words:
            mid_x = (w["x0"] + w["x1"]) / 2
            vertical_distance = w["top"] - label_y
            if (
                label_x0 <= mid_x <= label_x1 and
                0 < vertical_distance <= max_distance_below and
                is_potential_invoice_number(w["text"])
            ):
                print(f"[DEBUG] Candidate from label {label_idx}: {w['orig']} (Δy={vertical_distance:.1f})")
                if vertical_distance < best_score:
                    best_score = vertical_distance
                    best_candidate = w

    if best_candidate:
        print(f"[DEBUG] Invoice Number (below fallback best): {best_candidate['orig']}")
        return best_candidate["orig"].lstrip("#:").strip()

    print("[DEBUG] No label match or fallback for Invoice Number.")
    return ""

def is_potential_invoice_number(text):
    print(f"[DEBUG] Testing invoice candidate: '{text}'")
    return re.match(r"^#?(?:[A-Z]{1,4}-?)?[0-9]{3,}[A-Z0-9\-]*$", text.strip(), re.IGNORECASE)

# ------------------ Invoice Date Extractor ------------------

def extract_invoice_date(words):
    text_blob = " ".join([w["text"] for w in words])
    print("\n[DEBUG] Combined text_blob:\n", text_blob)

    # --- Regex setup ---
    MONTH_NAMES = [
        "Jan(?:uary)?", "Feb(?:ruary)?", "Mar(?:ch)?", "Apr(?:il)?", "May", "Jun(?:e)?",
        "Jul(?:y)?", "Aug(?:ust)?", "Sep(?:t(?:ember)?)?", "Oct(?:ober)?",
        "Nov(?:ember)?", "Dec(?:ember)?"
    ]

    patterns = [
        r"\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12][0-9]|3[01])[/-](?:\d{2}|\d{4})\b",
        r"\b\d{4}[-](?:0?[1-9]|1[0-2])[-](?:0?[1-9]|[12][0-9]|3[01])\b",
        r"\b(?:{month})\s+\d{{1,2}},?\s+\d{{2,4}}\b".format(month="|".join(MONTH_NAMES)),
        r"\b\d{{1,2}}\s+(?:{month}),?\s+\d{{2,4}}\b".format(month="|".join(MONTH_NAMES)),
    ]
    combined_pattern = "|".join(patterns)

    # --- Date parsing ---
    matches = [match.group(0) for match in re.finditer(combined_pattern, text_blob, flags=re.IGNORECASE)]
    print("\n[DEBUG] Regex date matches found:")
    for m in matches:
        print(" -", m)

    today = datetime.today().date()
    MIN_VALID_DATE = datetime(today.year - 1, 1, 1).date()
    dates = set()

    for raw in matches:
        raw = raw.strip().replace(",", "")
        parsed = None
        print(f"\n[DEBUG] Trying to parse: {raw}")

        for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d",
                    "%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y",
                    "%B %d %y", "%b %d %y", "%d %B %y", "%d %b %y"):
            try:
                parsed = datetime.strptime(raw, fmt).date()
                print(f"   ✓ Parsed as {parsed} using format: {fmt}")
                break
            except ValueError:
                continue

        if parsed:
            if MIN_VALID_DATE <= parsed <= today:
                dates.add(parsed)
                print(f"   → Added to date list: {parsed}")
            else:
                print(f"   ✗ Skipped: date {parsed} is outside valid range ({MIN_VALID_DATE} to {today})")
        else:
            print("   ✗ No format matched")

    if not dates:
        print("\n[DEBUG] No valid dates found.")
        return ""

    sorted_dates = sorted(dates)
    print("\n[DEBUG] Final valid dates (sorted):")
    for d in sorted_dates:
        print(" -", d.strftime("%m/%d/%y"))

    # --- Apply your 4-case logic ---
    if len(sorted_dates) == 1:
        print("\n[DEBUG] Case 1: Only 1 date found.")
        return sorted_dates[0].strftime("%m/%d/%y")

    elif len(sorted_dates) == 2:
        delta = abs((sorted_dates[0] - sorted_dates[1]).days)
        print(f"\n[DEBUG] Case 2 or 3: Two dates found with delta {delta} days.")
        if delta <= 7:
            print("→ Case 2: Using later date as invoice date.")
            return max(sorted_dates).strftime("%m/%d/%y")
        elif delta >= 30:
            print("→ Case 3: Using earlier date as invoice date.")
            return min(sorted_dates).strftime("%m/%d/%y")
        else:
            print("→ Ambiguous range: defaulting to earlier date.")
            return min(sorted_dates).strftime("%m/%d/%y")

    else:
        print(f"\n[DEBUG] Case 4: {len(sorted_dates)} dates found.")
        for i in range(len(sorted_dates)):
            for j in range(i + 1, len(sorted_dates)):
                if abs((sorted_dates[i] - sorted_dates[j]).days) <= 7:
                    invoice_date = max(sorted_dates[i], sorted_dates[j])
                    print("→ Found pair within 7 days — using later one as invoice date.")
                    return invoice_date.strftime("%m/%d/%y")
        print("→ No pairs close together: using earliest as invoice date.")
        return sorted_dates[0].strftime("%m/%d/%y")

# ------------------ Discount Terms Extractor WIP ------------------

def extract_discount_terms(words):
    for i, word in enumerate(words):
        if "terms" in word["text"].lower():
            for offset in range(1, 5):
                if i + offset < len(words):
                    value = words[i + offset]["text"]
                    if re.search(r"\d+%.*NET.*\d+", value.upper()):
                        print(f"[DEBUG] Found Discount Terms: {value}")
                        return value.upper()
    return ""

# ------------------ Total Amount Extractor WIP ------------------

def extract_total_amount(words):
    for i, word in enumerate(words):
        if "total" in word["text"].lower():
            for offset in range(1, 5):
                if i + offset < len(words):
                    value = words[i + offset]["text"]
                    if re.match(r"^\$?\d+[,.]?\d*$", value):
                        print(f"[DEBUG] Found Total Amount: {value}")
                        return clean_currency(value)
    return ""

# ------------------ Vendor Extractor WIP ------------------

def extract_vendor(words):
    candidates = [w["text"] for w in words if w["top"] < 150]
    if candidates:
        best_guess = candidates[0]
        print(f"[DEBUG] Guessed Vendor Name: {best_guess}")
        return best_guess
    return ""

# ------------------ Utilities ------------------

def normalize_date(date_str):
    for fmt in ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d", "%m-%d-%Y"):
        try:
            return datetime.strptime(date_str, fmt).strftime("%Y-%m-%d")
        except:
            continue
    return date_str  # fallback

def clean_currency(value):
    return value.replace("$", "").replace(",", "").strip()

def calculate_discount_fields(terms, invoice_date, total_amount):
    m = re.match(r"(\d+)%\s*(\d+)\s*NET\s*(\d+)", terms)
    if not m:
        raise ValueError("Could not parse discount terms")

    discount_percent = float(m.group(1)) / 100
    discount_days = int(m.group(2))

    try:
        inv_date = datetime.strptime(invoice_date, "%Y-%m-%d")
    except ValueError:
        raise ValueError("Invalid invoice date format")

    discount_due = inv_date + timedelta(days=discount_days)
    total = float(total_amount)
    discounted_total = round(total * (1 - discount_percent), 2)

    return discount_due.strftime("%Y-%m-%d"), f"{discounted_total:.2f}"
