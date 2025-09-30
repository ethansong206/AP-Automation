import re
import os
import csv
from .utils import (
    get_vendor_list,
    normalize_vendor_name,
    normalize_string,
    load_manual_mapping,
)
from utils import get_vendor_csv_path
from logging_config import get_logger

logger = get_logger(__name__)

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
    logger.debug(f"Reloaded {len(VENDOR_NAMES)} vendors and {len(MANUAL_MAP)} manual mappings")

def extract_vendor_name(words):
    all_words = [w["text"] for w in words]
    normalized_blob = normalize_string(" ".join(all_words))
    
    logger.debug(f"Normalized text blob ({len(normalized_blob)} chars): '{normalized_blob[:200]}{'...' if len(normalized_blob) > 200 else ''}'")
    logger.debug(f"Checking {len(MANUAL_MAP)} manual identifiers for matches...")

    # --- Check Manual Mapping First ---
    for key, value in MANUAL_MAP.items():
        logger.debug(f"Checking identifier '{key}' against text blob...")
        if key in normalized_blob:
            logger.debug(f"✓ Manual identifier match found: '{key}' → vendor '{value}'")
            return value
        #else:
            logger.debug(f"✗ No match for identifier '{key}'")

    logger.debug("No manual identifier matches found, proceeding to direct vendor name matching...")

    # --- Direct exact match: consecutive multi-word groups (2 to 6) ---
    for n in range(6, 1, -1):  # Start with longest chains first
        for i in range(len(all_words) - n + 1):
            group = " ".join(all_words[i:i+n])
            norm = normalize_vendor_name(group)

            # --- Hardcoded skip for Gray L edge-case \\\ Remove and improve later ---
            if norm.replace(" ", "") == "grayl":
                #print(f"[DEBUG] Skipping false match for normalized 'grayl'")
                continue

            if norm in NORMALIZED_VENDOR_NAMES:
                idx = NORMALIZED_VENDOR_NAMES.index(norm)
                logger.debug(f"Multi-word vendor match found: {VENDOR_NAMES[idx]}")
                return VENDOR_NAMES[idx]

    # --- Fallback: Direct exact match for single words ---
    for word in all_words:
        norm = normalize_vendor_name(word)
        if norm in NORMALIZED_VENDOR_NAMES:
            idx = NORMALIZED_VENDOR_NAMES.index(norm)
            logger.debug(f"Single-word vendor match found: {VENDOR_NAMES[idx]}")
            return VENDOR_NAMES[idx]

    logger.debug(f"No vendor match found for text blob containing {len(all_words)} words")
    return ""


def save_manual_mapping(key, vendor_name):
    """Add a new identifier mapping by appending a row to the vendors CSV."""    
    csv_path = get_vendor_csv_path()
    identifier = key.strip()
    vendor = vendor_name.strip()
    
    if not identifier or not vendor:
        #print(f"[ERROR] Cannot save manual mapping with empty identifier or vendor name")
        return
    
    try:
        # Check if this mapping already exists
        existing_mappings = load_manual_mapping()
        normalized_key = normalize_string(identifier)
        if normalized_key in existing_mappings:
            if existing_mappings[normalized_key] == vendor:
                #print(f"[INFO] Mapping already exists: '{identifier}' → '{vendor}'")
                return
            #else:
                #print(f"[INFO] Updating existing mapping: '{identifier}' → '{vendor}'")
        
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
        
        logger.info(f"Saved manual mapping: '{identifier}' → '{vendor}'")
        
        # Reload the manual mapping cache since we just changed the CSV
        global MANUAL_MAP
        MANUAL_MAP = load_manual_mapping()
        
    except Exception as e:
        logger.error(f"Failed to save manual mapping: {e}")
