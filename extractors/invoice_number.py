import re

def extract_invoice_number(words, vendor_name):
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

    # Existing single-word label
    for idx, w in enumerate(normalized_words):
        if w["text"] == "invoice":
            # Skip if "original" is directly before "invoice"
            if idx > 0 and normalized_words[idx - 1]["text"] == "original":
                continue
            # Skip if "date" or "date:" is directly after "invoice" and "invoice" is not "invoice:"
            # But do NOT skip for Prism Designs
            if (
                vendor_name != "Prism Designs" and
                idx < len(normalized_words) - 1 and
                normalized_words[idx + 1]["text"] in ["date", "date:"] and
                w["orig"].strip().lower() not in ["invoice:", "invoice:"]  # check original text for colon
            ):
                continue
            label_positions.append((w["x0"], w["x1"], w["top"]))

    # Oboz-specific: add "number" as a label
    if vendor_name == "Oboz Footwear LLC":
        for idx, w in enumerate(normalized_words):
            if w["text"] == "number":
                label_positions.append((w["x0"], w["x1"], w["top"]))

    # New: Check for "credit memo" and "credit note" as two-word labels
    for i in range(len(normalized_words) - 1):
        first = normalized_words[i]
        second = normalized_words[i + 1]
        if (first["text"] == "credit" and second["text"] in ["memo", "note"]):
            # Combine their bounding boxes for the label position
            label_positions.append((first["x0"], second["x1"], first["top"]))

    # Prana-specific logic: check under the label "Reference"
    if vendor_name == "Prana Living LLC":
        print("[DEBUG] Checking for all 'reference' labels for Prana Living LLC")
        found_reference = False
        for idx, w in enumerate(normalized_words):
            if w["text"] == "reference":
                found_reference = True
                print(f"[DEBUG] Reference label at index={idx}, x0={w['x0']}, x1={w['x1']}, top={w['top']}, bottom={w['bottom']}")
                # Allow vertical overlap or small positive distance
                candidates = [
                    cand for cand in normalized_words
                    if (cand["x0"] >= w["x0"] - 100 and cand["x1"] <= w["x1"] + 100) and
                       -5 <= (cand["top"] - w["bottom"]) <= 300 and
                       is_potential_invoice_number(cand["text"], vendor_name)
                ]
                print(f"[DEBUG] Candidates found below 'reference': {[c['orig'] for c in candidates]}")
                if candidates:
                    best = sorted(candidates, key=lambda x: abs(x["top"] - w["bottom"]))[0]
                    print(f"[DEBUG] Invoice Number (below 'Reference' for Prana): {best['orig']}")
                    return best["orig"].lstrip("#:").strip()
                else:
                    print("[DEBUG] No valid invoice number found below this 'reference' label.")
        if not found_reference:
            print("[DEBUG] No 'reference' label found for Prana Living LLC.")

    for label_x0, label_x1, label_y in label_positions:
        candidates = [
            w for w in normalized_words
            if w["x0"] > label_x1 and abs(w["top"] - label_y) <= 5 and is_potential_invoice_number(w["text"], vendor_name)
        ]
        if candidates:
            best = sorted(candidates, key=lambda x: abs(x["top"] - label_y))[0]
            print(f"[DEBUG] Invoice Number (direct right match): {best['orig']}")
            return best["orig"].lstrip("#:").strip()

    for label_x0, label_x1, label_y in label_positions:
        candidates = [
            w for w in normalized_words
            if w["x0"] > label_x1 and abs(w["top"] - label_y) <= 20 and is_potential_invoice_number(w["text"], vendor_name)
        ]
        if candidates:
            best = sorted(candidates, key=lambda x: abs(x["top"] - label_y))[0]
            label_word = next(
                (w["text"] for w in words if abs(w["x0"] - label_x0) < 2 and abs(w["x1"] - label_x1) < 2 and abs(w["top"] - label_y) < 2),
                f"coords=({label_x0:.1f}, {label_y:.1f})"
            )
            print(f"[DEBUG] Invoice Number (loose right match from label '{label_word}'): {best['orig']}")
            return best["orig"].lstrip("#:").strip()

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
                        print(f"[DEBUG] Yakima candidate from label {label_idx}: {w['orig']} (Δy={vertical_distance:.1f})")
                        if vertical_distance < best_score:
                            best_score = vertical_distance
                            best_candidate = w

            # Generic case for other vendors
            elif (
                label_x0 <= mid_x <= label_x1 and
                0 < vertical_distance <= max_distance_below and
                is_potential_invoice_number(w["text"], vendor_name)
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

"""
def is_potential_invoice_number(text):
    print(f"[DEBUG] Testing invoice candidate: '{text}'")
    return re.match(r"^#?(?:[a-zA-Z]{1,4}-?)?[0-9]{3,}[a-zA-Z0-9\-]*$", text.strip(), re.IGNORECASE)
"""
    
def is_potential_invoice_number(text, vendor_name=None):
    print(f"[DEBUG] Testing invoice candidate: '{text}' for vendor '{vendor_name}'")
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