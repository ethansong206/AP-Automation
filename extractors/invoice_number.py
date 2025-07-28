# Bugs to fix:
# 1. The code does not handle invoice numbers that are Customer Copy Note (re: #019383163.pdf)
# 2. The code does not handle invoice numbers with alphabetical characters in the middle of the number (re: Yakima invoice / 250430_25CI0543356_3379_R3379_3379.pdf)
# 3. The code does not handle invoice numbers that are labeled "Transaction Number" (re: NiteIze / )

import re

def extract_invoice_number(words):
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

    for label_x0, label_x1, label_y in label_positions:
        candidates = [
            w for w in normalized_words
            if w["x0"] > label_x1 and abs(w["top"] - label_y) <= 5 and is_potential_invoice_number(w["text"])
        ]
        if candidates:
            best = sorted(candidates, key=lambda x: abs(x["top"] - label_y))[0]
            print(f"[DEBUG] Invoice Number (direct right match): {best['orig']}")
            return best["orig"].lstrip("#:").strip()

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