import re
from datetime import datetime, timedelta
import csv
import json
import os
import sys

# --- Resolve resource paths for dev and PyInstaller ---
def resource_path(relative_path):
    """
    Returns absolute path to resource.
    Handles both normal execution and PyInstaller bundles.
    """
    if getattr(sys, 'frozen', False):
        base_path = sys._MEIPASS  # Temporary directory in PyInstaller
    else:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)


# --- Clean currency strings like "$1,234.56" to "1234.56" ---
def clean_currency(value):
    return value.replace("$", "").replace(",", "").strip()


# --- Calculate due date based on NET terms ---
def calculate_discount_due_date(terms, invoice_date):
    """
    Parses discount terms and calculates due date based on NET terms.
    
    Args:
        terms (str): Payment terms string (e.g., "2% 10 NET 30", "NET 30")
        invoice_date (str): Invoice date string in supported format
        
    Returns:
        str: Due date in MM/DD/YY format or None if no NET term found
    """
    # Extract discount due date
    disc_match = re.search(r"(\d{2,3})\s*NET", terms, re.IGNORECASE)
    if not disc_match:
        net_match = re.search(r"NET\s*(\d+)", terms, re.IGNORECASE)
        if not net_match:
            return None
    if disc_match:
        net_days = int(disc_match.group(1))
    else:
        net_days = int(net_match.group(1))
    
    # Parse invoice date in multiple formats
    try:
        inv_date = datetime.strptime(invoice_date, "%Y-%m-%d")
    except ValueError:
        try:
            inv_date = datetime.strptime(invoice_date, "%m/%d/%y")
        except ValueError:
            raise ValueError("Invalid invoice date format")
    
    due_date = inv_date + timedelta(days=net_days)
    return due_date.strftime("%m/%d/%y")


# --- Calculate discounted total based on percentage in terms ---
def calculate_discounted_total(terms, total_amount, vendor_name):
    """
    Calculates the discounted total based on discount percentage in terms.
    
    Args:
        terms (str): Payment terms string (e.g., "2% 10 NET 30", "NET 30")
        total_amount (str): Total invoice amount
        
    Returns:
        str: Formatted discounted total or None if no discount percentage found
    """
    # Check for discount percentage
    discount_match = re.search(r"(\d+)%", terms)
    
    discount_percent = float(discount_match.group(1)) / 100
    return discount_total(discount_percent, total_amount)

def discount_total(discount_percent, total_amount):
    total = float(total_amount)
    discounted_total = round(total * (1 - discount_percent), 2)
    return f"{discounted_total:.2f}"


# --- Try parsing a raw date string with multiple common formats ---
def try_parse_date(raw):
    """
    Attempts to parse a wide range of date formats into a datetime.date object.
    """
    raw = raw.replace(",", "")
    for fmt in (
        "%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d",
        "%B %d %Y", "%b %d %Y", "%d %B %Y", "%d %b %Y",
        "%B %d %y", "%b %d %y", "%d %B %y", "%d %b %y",
        # New formats with dashes between components
        "%d-%b-%y", "%d-%b-%Y", "%d-%B-%y", "%d-%B-%Y",
    ):
        try:
            return datetime.strptime(raw, fmt).date()
        except ValueError:
            continue
    return None


# --- Load lowercase vendor names from vendors.csv into a set ---
def load_vendor_list():
    """
    Loads vendor names from vendors.csv as a lowercase set (used for fuzzy matching).
    """
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


# --- Load vendor names from vendors.csv as-is (for dropdown display) ---
def get_vendor_list():
    """
    Returns list of vendor names from vendors.csv.
    Used for dropdown selection (preserves formatting).
    """
    path = resource_path("data/vendors.csv")
    if not os.path.exists(path):
        return []

    with open(path, newline='', encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        return [row["Vendor Name"] for row in reader if row.get("Vendor Name")]


# --- Normalize vendor name: lowercase, remove suffixes and punctuation ---
def normalize_vendor_name(name):
    """
    Normalizes a vendor name by:
    - Lowercasing
    - Removing suffixes (llc, inc, etc.)
    - Stripping non-alphanumeric characters
    """
    name = name.lower()
    name = re.sub(r"\b(llc|inc|co|corp|ltd|company|corporation)\b", "", name)
    return re.sub(r"[^a-z0-9]", "", name)


# --- Normalize generic string (remove non-alphanum, preserve whitespace) ---
def normalize_string(text):
    """
    Lowercases and removes non-alphanumeric characters except whitespace.
    Used for consistent key formatting.
    """
    text = text.lower()
    return re.sub(r"[^a-z0-9\s]", "", text).strip()


# --- Load manual vendor map from JSON file ---
def load_manual_mapping():
    """
    Loads manual_vendor_map.json and normalizes keys.
    Returns a dictionary mapping identifier -> vendor name.
    """
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

# Check if Credit Memo amount is Negative, Flip Sign if Not
def check_negative_total(total_amount, discount_terms):
    total = float(total_amount)
    for term in ["CREDIT MEMO", "CREDIT NOTE", "WARRANTY", "RETURN AUTHORIZATION", "DEFECTIVE"]:
        if term == discount_terms:
            if total > 0:
                total = float(total * -1)
                return f"{total:.2f}"
        else:
            return f"{total:.2f}"