import re
import os
import csv
import logging
from .utils import (
    get_vendor_list,
    normalize_vendor_name,
    normalize_string,
    load_manual_mapping,
)
from utils import get_vendor_csv_path

# Load vendor names and manual map once
VENDOR_NAMES = get_vendor_list()
NORMALIZED_VENDOR_NAMES = [normalize_vendor_name(v) for v in VENDOR_NAMES]
MANUAL_MAP = load_manual_mapping()

def reload_vendor_cache():
    """Reload vendor names and identifier mappings from vendors.csv."""
    global VENDOR_NAMES, NORMALIZED_VENDOR_NAMES, MANUAL_MAP
    VENDOR_NAMES = get_vendor_list()
    NORMALIZED_VENDOR_NAMES = [normalize_vendor_name(v) for v in VENDOR_NAMES]
    MANUAL_MAP = load_manual_mapping()
    logging.debug("Reloaded %d vendors and %d manual mappings", len(VENDOR_NAMES), len(MANUAL_MAP))

def extract_vendor_name(words):
    all_words = [w["text"] for w in words]
    normalized_blob = normalize_string(" ".join(all_words))
    
    logging.debug("Normalized text blob (%d chars): '%s%s'", len(normalized_blob), normalized_blob[:200], '...' if len(normalized_blob) > 200 else '')
    logging.debug("Checking %d manual identifiers for matches...", len(MANUAL_MAP))

    # --- Check Manual Mapping First ---
    for key, value in MANUAL_MAP.items():
        logging.debug("Checking identifier '%s' against text blob...", key)
        if key in normalized_blob:
            logging.debug("✓ Manual identifier match found: '%s' → vendor '%s'", key, value)
            return value
        else:
            logging.debug("✗ No match for identifier '%s'", key)

    logging.debug("No manual identifier matches found, proceeding to direct vendor name matching...")

    # --- Direct exact match: consecutive multi-word groups (2 to 6) ---
    for n in range(6, 1, -1):  # Start with longest chains first
        for i in range(len(all_words) - n + 1):
            group = " ".join(all_words[i:i+n])
            norm = normalize_vendor_name(group)

            # --- Hardcoded skip for Gray L edge-case \\\ Remove and improve later ---
            if norm.replace(" ", "") == "grayl":
                logging.debug("Skipping false match for normalized 'grayl'")
                continue

            if norm in NORMALIZED_VENDOR_NAMES:
                idx = NORMALIZED_VENDOR_NAMES.index(norm)
                logging.debug("Multi-word vendor match found: %s", VENDOR_NAMES[idx])
                return VENDOR_NAMES[idx]

    # --- Fallback: Direct exact match for single words ---
    for word in all_words:
        norm = normalize_vendor_name(word)
        if norm in NORMALIZED_VENDOR_NAMES:
            idx = NORMALIZED_VENDOR_NAMES.index(norm)
            logging.debug("Single-word vendor match found: %s", VENDOR_NAMES[idx])
            return VENDOR_NAMES[idx]

    logging.debug("No vendor match found for text blob containing %d words", len(all_words))
    return ""


def save_manual_mapping(key, vendor_name):
    """Add a new identifier mapping by appending a row to the vendors CSV."""    
    csv_path = get_vendor_csv_path()
    identifier = key.strip()
    vendor = vendor_name.strip()
    
    if not identifier or not vendor:
        logging.error("Cannot save manual mapping with empty identifier or vendor name")
        return
    
    try:
        # Check if this mapping already exists
        existing_mappings = load_manual_mapping()
        normalized_key = normalize_string(identifier)
        if normalized_key in existing_mappings:
            if existing_mappings[normalized_key] == vendor:
                logging.info("Mapping already exists: '%s' → '%s'", identifier, vendor)
                return
            else:
                logging.info("Updating existing mapping: '%s' → '%s'", identifier, vendor)
        
        # Read existing CSV data
        rows = []
        if os.path.exists(csv_path):
            with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
        
        # Add new row with identifier (no vendor number since this is a manual mapping)
        new_row = {
            "Vendor No. (Sage)": "",  # Manual mappings don't need vendor numbers
            "Vendor Name": vendor,
            "Identifier": identifier
        }
        rows.append(new_row)
        
        # Sort by vendor name, then identifier
        rows.sort(key=lambda r: (r["Vendor Name"].lower(), r.get("Identifier", "").lower()))
        
        # Write back to CSV
        with open(csv_path, "w", encoding="utf-8", newline="") as f:
            fieldnames = ["Vendor No. (Sage)", "Vendor Name", "Identifier"]
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        
        logging.info("Saved manual mapping: '%s' → '%s'", identifier, vendor)
        
        # Reload the manual mapping cache since we just changed the CSV
        global MANUAL_MAP
        MANUAL_MAP = load_manual_mapping()
        
    except Exception as e:
        logging.error("Failed to save manual mapping: %s", e)
