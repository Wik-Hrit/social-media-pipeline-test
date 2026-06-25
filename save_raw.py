import json
import os
import logging
from filenamegen import generate_filename

log = logging.getLogger(__name__)

def save_raw(query, data):
    filepath = generate_filename(query, folder="raw")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # Fix #7 — exception handling around json.dump
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        log.info(f"  ✓ Raw response saved → {filepath}")
    except Exception as e:
        log.error(f"  ✗ Failed to save raw data: {e}")
        return None

    return filepath