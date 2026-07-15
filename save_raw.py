import json
import os
import logging
from filenamegen import generate_filename

log = logging.getLogger(__name__)

_INTERNAL = {"_source", "_page_no"}

def save_raw(query, data):
    # Fix 15: empty response guard
    if not data.get("tweets"):
        log.warning(f"  No tweets for '{query}' — skipping raw save")
        return None

    # Fix 14: strip internal pipeline fields from raw files
    clean_data = {
        **data,
        "tweets": [{k: v for k, v in t.items() if k not in _INTERNAL}
                   for t in data.get("tweets", [])]
    }

    filepath = generate_filename(query, folder="raw")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(clean_data, f, ensure_ascii=False, indent=2)
        log.info(f"  ✓ Raw response saved → {filepath}")
    except Exception as e:
        log.error(f"  ✗ Failed to save raw data: {e}")
        return None

    return filepath