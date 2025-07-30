# Bugs to fix:
# 1. The code does not handle invoice dates well in multiple-unique-dates cases. (re: Dapper Ink, Yakima)

import re
from datetime import datetime
from .utils import try_parse_date

def extract_invoice_date(words, vendor_name):
    text_blob = " ".join([w["text"] for w in words])

    MONTH_NAMES = [
        "Jan(?:uary)?", "Feb(?:ruary)?", "Mar(?:ch)?", "Apr(?:il)?", "May", "Jun(?:e)?",
        "Jul(?:y)?", "Aug(?:ust)?", "Sep(?:t(?:ember)?)?", "Oct(?:ober)?",
        "Nov(?:ember)?", "Dec(?:ember)?"
    ]

    patterns = [
        r"\b(?:0?[1-9]|1[0-2])[/-](?:0?[1-9]|[12][0-9]|3[01])[/-](?:\d{2}|\d{4})\b",
        r"\b\d{4}[-](?:0?[1-9]|1[0-2])[-](?:0?[1-9]|3[01])\b",
        r"\b(?:{month})\s+\d{{1,2}},?\s+\d{{2,4}}\b".format(month="|".join(MONTH_NAMES)),
        r"\b\d{{1,2}}\s+(?:{month}),?\s+\d{{2,4}}\b".format(month="|".join(MONTH_NAMES)),
    ]
    combined_pattern = "|".join(patterns)

    matches = [match.group(0) for match in re.finditer(combined_pattern, text_blob, flags=re.IGNORECASE)]
    print("\n[DEBUG] Regex date matches found:")
    for m in matches:
        print(" -", m)

    today = datetime.today().date()
    MIN_VALID_DATE = datetime(today.year, max(1, today.month - 3), 1).date() # Only consider dates within the last 3 months
    date_matches = []

    for raw in matches:
        raw_clean = raw.strip().replace(",", "")
        parsed = try_parse_date(raw_clean)
        if parsed:
            if MIN_VALID_DATE <= parsed <= today:
                date_matches.append(parsed)
                print(f"   ✓ Accepted valid date: {parsed}")
            else:
                print(f"   ✗ Skipped date {parsed}, out of range")
        else:
            print(f"   ✗ Could not parse: {raw_clean}")

    if not date_matches:
        print("[DEBUG] No valid dates found.")
        return ""

    # Remove duplicates by converting to set and back to list
    date_matches = list(set(date_matches))
    sorted_dates = sorted(date_matches)
    print("[DEBUG] Final valid dates (de-duped & sorted):", [d.strftime("%m/%d/%y") for d in sorted_dates])

    # --- Apply your 4-case logic ---
    if len(sorted_dates) == 1:
        print("[DEBUG] Case 1: One date found.")
        return sorted_dates[0].strftime("%m/%d/%y")

    elif len(sorted_dates) == 2:
        delta = abs((sorted_dates[0] - sorted_dates[1]).days)
        if delta <= 7:
            return max(sorted_dates).strftime("%m/%d/%y")
        elif delta >= 30:
            return min(sorted_dates).strftime("%m/%d/%y")
        else:
            return min(sorted_dates).strftime("%m/%d/%y")

    else:
        for i in range(len(sorted_dates)):
            for j in range(i + 1, len(sorted_dates)):
                if abs((sorted_dates[i] - sorted_dates[j]).days) <= 7:
                    return max(sorted_dates[i], sorted_dates[j]).strftime("%m/%d/%y")
        return sorted_dates[0].strftime("%m/%d/%y")