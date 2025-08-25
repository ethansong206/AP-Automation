import re
from datetime import datetime, timedelta
import csv
import os
import logging

from utils import get_vendor_csv_path


# --- Clean currency strings like "$1,234.56" to "1234.56" ---
def clean_currency(value):
    return value.replace("$", "").replace(",", "").strip()


# --- Calculate due date based on payment terms ---
def calculate_discount_due_date(terms, invoice_date):
    """
    Parse payment terms and calculate the due date. Supports terms with
    or without the explicit word "NET" (e.g., "2% 10 NET 30", "8% 75", "NET 30").
    
    Args:
        terms (str): Payment terms string.
        invoice_date (str): Invoice date string in supported format.
        
    Returns:
        str: Due date in MM/DD/YY format or None if no days can be determined.
    """
    terms_upper = terms.upper()

    # Collect candidate day values ignoring numbers tied to percentages.
    candidates = []
    for m in re.finditer(r"\d+", terms_upper):
        idx = m.end()
        # Skip any whitespace after the number
        while idx < len(terms_upper) and terms_upper[idx].isspace():
            idx += 1
        # If the next non-space character is a percent sign, skip this number
        if idx < len(terms_upper) and terms_upper[idx] == '%':
            continue
        candidates.append(int(m.group()))

    if not candidates:
        return None

    # Default to the smallest non-percent number
    net_days = min(candidates)

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


# --- Load vendor names from vendors.csv as-is (for dropdown display) ---
def get_vendor_list():
    """
    Returns list of vendor names from vendors.csv.
    Used for dropdown selection (preserves formatting).
    """
    csv_path = get_vendor_csv_path()
    if not os.path.exists(csv_path):
        return []

    with open(csv_path, newline='', encoding="utf-8") as csvfile:
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
    Loads manual identifier mappings from vendors.csv.
    Returns a dictionary mapping normalized identifier -> vendor name.
    """
    # Use direct path to Roaming root where vendors.csv actually is
    csv_path = get_vendor_csv_path()
    
    if os.path.exists(csv_path):
        try:
            mapping = {}
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    identifier = (row.get("Identifier", "") or "").strip()
                    vendor_name = (row.get("Vendor Name", "") or "").strip()
                    
                    # Only add mappings where both identifier and vendor name exist
                    if identifier and vendor_name:
                        # Normalize the identifier key like before
                        normalized_key = normalize_string(identifier)
                        mapping[normalized_key] = vendor_name
            
            logging.info("Loaded %d manual vendor mappings from CSV", len(mapping))
            return mapping
        except Exception as e:
            logging.error("Failed to load vendor CSV for identifiers: %s", e)
            return {}
    else:
        logging.warning("Vendor CSV not found at %s", csv_path)
        return {}

# Check if Credit Memo amount is Negative, Flip Sign if Not
def check_negative_total(total_amount, discount_terms):
    total = float(total_amount)
    for term in ["CREDIT MEMO", "CREDIT NOTE", "WARRANTY", "RETURN AUTHORIZATION", "DEFECTIVE"]:
        if term == discount_terms:
            if total > 0:
                total = float(total * -1)
            return f"{total:.2f}"
    return f"{total:.2f}"