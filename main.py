from fetch_tweets import fetch_tweets
from save_raw import save_raw
from save_processed import save_processed
from paginator import fetch_all_pages
from datetime import datetime
import time

# ============================================================
# LOAD QUERIES FROM FILE
# ============================================================
with open("queries.txt", "r") as f:
    queries = [line.strip() for line in f if line.strip()]

print(f"Loaded {len(queries)} queries from queries.txt")

# ============================================================
# SETTINGS
# ============================================================
QUERY_TYPE = "Latest"
COUNT = 20
USE_PAGINATION = True

# ============================================================
# MAIN PIPELINE
# ============================================================
print(f"Pipeline started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

for query in queries:
    print(f"\n{'='*50}")
    print(f"Query: '{query}'")
    print(f"{'='*50}")

    if USE_PAGINATION:
        tweets = fetch_all_pages(query, QUERY_TYPE, max_pages=3)
        data = {"tweets": tweets}
    else:
        success, data = fetch_tweets(query, QUERY_TYPE, COUNT)
        if not success:
            continue

    save_raw(query, data)
    save_processed(query, data)
    time.sleep(5)

print(f"\nPipeline completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")