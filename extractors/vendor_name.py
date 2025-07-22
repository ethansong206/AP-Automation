def extract_vendor(words):
    candidates = [w for w in words if w["top"] < 150]
    if candidates:
        best_guess = candidates[0]
        print(f"[DEBUG] Guessed Vendor Name: {best_guess['text']}")
        return best_guess["text"]
    return ""