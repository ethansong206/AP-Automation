import re
from .utils import clean_currency

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