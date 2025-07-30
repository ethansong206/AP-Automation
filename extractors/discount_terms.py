import re

def extract_discount_terms(words, vendor_name):
    for i, word in enumerate(words):
        if "terms" in word["text"].lower():
            for offset in range(1, 5):
                if i + offset < len(words):
                    value = words[i + offset]["text"]
                    if re.search(r"\d+%.*NET.*\d+", value.upper()):
                        print(f"[DEBUG] Found Discount Terms: {value}")
                        return value.upper()
    return ""