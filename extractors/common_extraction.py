import re

def normalize_words(words, first_page_only=True):
    """
    Normalize words by filtering to first page (optional) and standardizing text format
    """
    if first_page_only:
        filtered_words = [w for w in words if w.get("page_num", 0) == 0]
        #print(f"[DEBUG] Using page_num == 0 to restrict to first page")
        #print(f"[DEBUG] Retained {len(filtered_words)} words for first-page check")
    else:
        filtered_words = words
        
    return [
        {
            "index": i,
            "text": w["text"].strip().lower().replace(":", "").replace("#", ""),
            "orig": w["text"],
            "x0": w["x0"],
            "x1": w["x1"],
            "top": w["top"],
            "bottom": w["bottom"]
        }
        for i, w in enumerate(filtered_words)
    ]

def find_label_positions(normalized_words, label_type="invoice", custom_label=None):
    """
    Find positions of specified label type (invoice or po) or a custom label.
    Returns a list of (x0, x1, top, bottom) tuples.
    """
    label_positions = []

    def normalize_label(text):
        import string
        return "".join(c for c in text.lower() if c not in string.punctuation).strip()

    if custom_label:
        custom_label_norm = normalize_label(custom_label)
        for w in normalized_words:
            if normalize_label(w["orig"]) == custom_label_norm:
                label_positions.append((w["x0"], w["x1"], w["top"], w["bottom"]))
        return label_positions

    # Two-word labels (e.g., "invoice #", "po number")
    for i in range(len(normalized_words) - 1):
        first = normalized_words[i]
        second = normalized_words[i + 1]
        if first["text"] == label_type and second["text"] in ["#", "no", "number"]:
            label_positions.append((first["x0"], second["x1"], second["top"]))
    
    # Single-word labels
    if label_type == "invoice":
        for idx, w in enumerate(normalized_words):
            if w["text"] == "invoice":
                # Skip if "original" is directly before "invoice"
                if idx > 0 and normalized_words[idx - 1]["text"] == "original":
                    continue
                # Skip if "date" or "date:" is directly after "invoice" and "invoice" is not "invoice:"
                if (
                    idx < len(normalized_words) - 1 and
                    normalized_words[idx + 1]["text"] in ["date", "date:"] and
                    w["orig"].strip().lower() not in ["invoice:", "invoice:"]
                ):
                    continue
                label_positions.append((w["x0"], w["x1"], w["top"]))
    
    # For PO labels, include "purchase order" as two-word label
    if label_type == "po":
        for i in range(len(normalized_words) - 1):
            first = normalized_words[i]
            second = normalized_words[i + 1]
            if first["text"] == "purchase" and second["text"] == "order":
                label_positions.append((first["x0"], second["x1"], first["top"]))
        
        # Single-word PO labels
        for idx, w in enumerate(normalized_words):
            if w["text"] == "po":
                label_positions.append((w["x0"], w["x1"], w["top"]))
    
    return label_positions

def find_value_to_right(normalized_words, label_positions, validation_func, strict=True):
    """
    Find a value to the right of any label in label_positions
    """
    # Strict matching (very close horizontally)
    for pos in label_positions:
        # Extract only the needed values using slicing
        label_x0, label_x1, label_y = pos[0], pos[1], pos[2]
        
        candidates = [
            w for w in normalized_words
            if w["x0"] > label_x1 and abs(w["top"] - label_y) <= 5 and validation_func(w["text"])
        ]
        if candidates:
            best = sorted(candidates, key=lambda x: abs(x["top"] - label_y))[0]
            #print(f"[DEBUG] Value (direct right match): {best['orig']}")
            return best["orig"].lstrip("#:").strip()
    
    # Looser matching if strict didn't find anything
    if not strict:
        for pos in label_positions:
            label_x0, label_x1, label_y = pos[0], pos[1], pos[2]
            
            candidates = [
                w for w in normalized_words
                if w["x0"] > label_x1 and abs(w["top"] - label_y) <= 20 and validation_func(w["text"])
            ]
            if candidates:
                best = sorted(candidates, key=lambda x: abs(x["top"] - label_y))[0]
                return best["orig"].lstrip("#:").strip()
    
    return None

def find_value_below(normalized_words, label_positions, validation_func, max_distance=150):
    """
    Find a value below any label in label_positions
    """
    best_candidate = None
    best_score = float("inf")

    for label_idx, (label_x0, label_x1, label_y) in enumerate(label_positions):
        for w in normalized_words:
            mid_x = (w["x0"] + w["x1"]) / 2
            vertical_distance = w["top"] - label_y
            
            if (
                label_x0 <= mid_x <= label_x1 and
                0 < vertical_distance <= max_distance and
                validation_func(w["text"])
            ):
                if vertical_distance < best_score:
                    best_score = vertical_distance
                    best_candidate = w
    
    if best_candidate:
        #print(f"[DEBUG] Value (below fallback best): {best_candidate['orig']}")
        return best_candidate["orig"].lstrip("#:").strip()
    
    return None

def search_for_pattern(normalized_words, pattern, case_sensitive=False):
    """
    Search for words matching a specific regex pattern
    """
    flags = 0 if case_sensitive else re.IGNORECASE
    matches = [w for w in normalized_words if re.match(pattern, w["orig"].strip(), flags)]
    
    if matches:
        #print(f"[DEBUG] Pattern match found: {matches[0]['orig']}")
        return matches[0]["orig"].strip()
    
    return None