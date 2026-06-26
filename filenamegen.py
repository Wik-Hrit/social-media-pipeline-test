from datetime import datetime

def generate_filename(query, folder="raw"):
    now        = datetime.now()
    date_str   = now.strftime("%Y-%m-%d")          # e.g. 2026-06-27
    timestamp  = now.strftime("%Y%m%d_%H%M%S")     # e.g. 20260627_011832
    clean_query = query.replace(" ", "-").lower()
    filename   = f"{clean_query}_{timestamp}.json"
    return f"data/{folder}/{date_str}/{filename}"   # date-based subfolder