"""
main.py — Twitter acquisition pipeline entry point.
Fix #6: All settings imported from config.py
Fix #7: print() replaced with log.*()
Fix #8: pipeline version, query type, page no included in metadata
Scheduler: auto-reruns every RUN_INTERVAL_HOURS hours
"""

import logging
import time
from datetime import datetime
from config import *
from fetch_tweets import fetch_tweets
from save_raw import save_raw
from save_processed import save_processed
from paginator import fetch_all_pages
from twitter_client import check_credits

# ── Logging setup ─────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)


def load_queries():
    """Load and deduplicate queries from file."""
    with open(QUERIES_FILE, "r") as f:
        raw_queries = [line.strip() for line in f if line.strip()]
    queries = list(dict.fromkeys(raw_queries))
    if len(queries) < len(raw_queries):
        log.warning(f"Removed {len(raw_queries) - len(queries)} duplicate queries")
    log.info(f"Loaded {len(queries)} queries from {QUERIES_FILE}")
    return queries


def run_pipeline(queries, run_number):
    """Run one full pipeline pass over all queries."""
    log.info(f"{'#'*50}")
    log.info(f"RUN #{run_number} started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    log.info(f"Pipeline version: {PIPELINE_VERSION} | Query type: {QUERY_TYPE} | Pagination: {USE_PAGINATION}")
    log.info(f"{'#'*50}")

    # Check credits before starting run
    try:
        check_credits()
    except RuntimeError as e:
        log.error(f"Stopping pipeline: {e}")
        return

    for query in queries:
        log.info(f"{'='*50}")
        log.info(f"Query: '{query}'")
        log.info(f"{'='*50}")

        meta = {
            "pipeline_version": PIPELINE_VERSION,
            "query_type":       QUERY_TYPE,
            "use_pagination":   USE_PAGINATION,
            "run_number":       run_number,
            "query":            query,
            "fetchedAt":        datetime.now().isoformat(),
        }

        if USE_PAGINATION:
            tweets, source = fetch_all_pages(query, QUERY_TYPE, max_pages=MAX_PAGES)
            data = {"tweets": tweets, "meta": meta}
        else:
            success, data, source = fetch_tweets(query, QUERY_TYPE, COUNT)
            if not success:
                log.warning(f"Skipping query: '{query}'")
                time.sleep(QUERY_DELAY)
                continue
            data["meta"] = meta

        save_raw(query, data)
        save_processed(query, data, source)
        time.sleep(QUERY_DELAY)

    log.info(f"RUN #{run_number} completed at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


# ── Scheduler ─────────────────────────────────────────────────────────────────
queries    = load_queries()
run_number = 1

if not SCHEDULER_ENABLED:
    # Single run mode
    run_pipeline(queries, run_number)
else:
    log.info(f"Scheduler enabled — running every {RUN_INTERVAL_HOURS}h | Max runs: {'∞' if MAX_RUNS == 0 else MAX_RUNS}")
    while True:
        # Reload queries each run so you can update queries.txt without restarting
        queries = load_queries()
        run_pipeline(queries, run_number)

        if MAX_RUNS > 0 and run_number >= MAX_RUNS:
            log.info(f"Reached max runs ({MAX_RUNS}). Stopping.")
            break

        next_run = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        wait_seconds = RUN_INTERVAL_HOURS * 3600
        log.info(f"Next run in {RUN_INTERVAL_HOURS}h — sleeping until then. Press Ctrl+C to stop.")

        try:
            time.sleep(wait_seconds)
        except KeyboardInterrupt:
            log.info("Scheduler stopped by user.")
            break

        run_number += 1