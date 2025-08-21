import re
from .utils import get_vendor_list, normalize_vendor_name, normalize_string, load_manual_mapping
import os
import json

from utils import get_manual_map_path

# Load vendor names and manual map once
VENDOR_NAMES = get_vendor_list()
NORMALIZED_VENDOR_NAMES = [normalize_vendor_name(v) for v in VENDOR_NAMES]
MANUAL_MAP = load_manual_mapping()


def extract_vendor_name(words):
    all_words = [w["text"] for w in words]
    normalized_blob = normalize_string(" ".join(all_words))

    # --- Check Manual Mapping First ---
    for key, value in MANUAL_MAP.items():
        if key in normalized_blob:
            print(f"[DEBUG] Manual match found for '{key}' → {value}")
            return value

    # --- Direct exact match: consecutive multi-word groups (2 to 6) ---
    for n in range(6, 1, -1):  # Start with longest chains first
        for i in range(len(all_words) - n + 1):
            group = " ".join(all_words[i:i+n])
            norm = normalize_vendor_name(group)

            # --- Hardcoded skip for Gray L edge-case \\\ Remove and improve later ---
            if norm.replace(" ", "") == "grayl":
                print(f"[DEBUG] Skipping false match for normalized 'grayl'")
                continue

            if norm in NORMALIZED_VENDOR_NAMES:
                idx = NORMALIZED_VENDOR_NAMES.index(norm)
                print(f"[DEBUG] Multi-word vendor match found: {VENDOR_NAMES[idx]}")
                return VENDOR_NAMES[idx]

    # --- Fallback: Direct exact match for single words ---
    for word in all_words:
        norm = normalize_vendor_name(word)
        if norm in NORMALIZED_VENDOR_NAMES:
            idx = NORMALIZED_VENDOR_NAMES.index(norm)
            print(f"[DEBUG] Single-word vendor match found: {VENDOR_NAMES[idx]}")
            return VENDOR_NAMES[idx]

    print("[DEBUG] No vendor match found.")
    return ""


def save_manual_mapping(key, vendor_name):
    json_path = get_manual_map_path()

    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            print(f"[ERROR] Failed to load manual vendor map for writing: {e}")
            data = {}
    else:
        data = {}

    normalized_key = normalize_string(key)
    data[normalized_key] = vendor_name.strip()

    try:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        print(f"[INFO] Saved manual mapping: '{key}' → '{vendor_name}'")
    except Exception as e:
        print(f"[ERROR] Failed to save manual mapping: {e}")
