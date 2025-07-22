import re
from datetime import datetime, timedelta

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
        try:
            inv_date = datetime.strptime(invoice_date, "%m/%d/%y")
        except ValueError:
            raise ValueError("Invalid invoice date format")

    discount_due = inv_date + timedelta(days=discount_days)
    total = float(total_amount)
    discounted_total = round(total * (1 - discount_percent), 2)

    return discount_due.strftime("%Y-%m-%d"), f"{discounted_total:.2f}"

def try_parse_date(raw):
    raw = raw.replace(",", "")
    for fmt in (
        "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d",
        "%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y",
        "%B %d %y", "%b %d %y", "%d %B %y", "%d %b %y"
    ):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None