import logging
import time
from datetime import datetime
from fetch_tweets import fetch_tweets
from save_raw import save_raw
from save_processed import save_processed
from paginator import fetch_all_pages

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

# ── Load & deduplicate queries (Fix #9) ───────────────────────────────────────
with open("queries.txt", "r") as f:
    raw_queries = [line.strip() for line in f if line.strip()]

queries = list(dict.fromkeys(raw_queries))  # preserve order, remove duplicates

if len(queries) < len(raw_queries):
    log.warning(f"Removed {len(raw_queries) - len(queries)} duplicate queries")

log.info(f"Loaded {len(queries)} queries from queries.txt")

# ── Settings ──────────────────────────────────────────────────────────────────
QUERY_TYPE    = "Latest"
COUNT         = 20
USE_PAGINATION = True

# ── Main pipeline ─────────────────────────────────────────────────────────────
log.info(f"Pipeline started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

for query in queries:
    log.info(f"{'='*50}")
    log.info(f"Query: '{query}'")
    log.info(f"{'='*50}")

    if USE_PAGINATION:
        tweets, source = fetch_all_pages(query, QUERY_TYPE, max_pages=3)
        data = {"tweets": tweets}
    else:
        success, data, source = fetch_tweets(query, QUERY_TYPE, COUNT)
        if not success:
            log.warning(f"Skipping query: '{query}'")
            continue

    save_raw(query, data)
    save_processed(query, data, source)
    time.sleep(5)

log.info(f"Pipeline completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")