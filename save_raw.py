import json
import os
from filenamegen import generate_filename

def save_raw(query, data):
    filepath = generate_filename(query, folder="raw")
    
    # Create folder if it doesn't exist
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"  ✓ Raw response saved → {filepath}")
    return filepath