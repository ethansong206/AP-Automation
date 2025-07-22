import re
from datetime import datetime, timedelta
import csv
import json
import os
import sys

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and PyInstaller bundle."""
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

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

def load_vendor_list():
    csv_path = resource_path("data/vendors.csv")

    vendor_set = set()
    if not os.path.exists(csv_path):
        print(f"[WARN] Vendor file not found: {csv_path}")
        return vendor_set

    with open(csv_path, newline='', encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            name = row.get("Vendor Name")
            if name:
                vendor_set.add(name.lower().strip())

    print(f"[INFO] Loaded {len(vendor_set)} known vendors")
    return vendor_set

def get_vendor_list():
    path = resource_path("data/vendors.csv")
    with open(path, newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        return [row["Vendor Name"] for row in reader if row.get("Vendor Name")]

def normalize_vendor_name(name):
    name = name.lower()
    name = re.sub(r"\b(llc|inc|co|corp|ltd|company|corporation)\b", "", name)
    return re.sub(r"[^a-z0-9]", "", name)

def normalize_string(text):
    text = text.lower()
    return re.sub(r"[^a-z0-9\s]", "", text).strip()

def load_manual_mapping():
    json_path = resource_path("data/manual_vendor_map.json")

    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                print(f"[INFO] Loaded {len(data)} manual vendor mappings")
                return {normalize_string(k): v.strip() for k, v in data.items()}
        except Exception as e:
            print(f"[ERROR] Failed to load manual map: {e}")
            return {}
    else:
        print(f"[WARN] Manual map not found at {json_path}")
        return {}