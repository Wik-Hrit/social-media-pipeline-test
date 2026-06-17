from datetime import datetime

def generate_filename(query, folder="raw"):
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_query = query.replace(" ", "-").lower()
    filename = f"{clean_query}_{timestamp}.json"
    return f"data/{folder}/{filename}"