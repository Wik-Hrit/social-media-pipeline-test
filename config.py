"""
config.py — Central configuration for the Twitter acquisition pipeline.
Fix #6: All settings moved here. Import with: from config import *
"""

# ── Pipeline version ──────────────────────────────────────────────────────────
PIPELINE_VERSION = "2.0.0"

# ── Query settings ────────────────────────────────────────────────────────────
QUERY_TYPE    = "Latest"   # "Latest" or "Top"
COUNT         = 20         # tweets per page
MAX_PAGES     = 3          # max pagination pages (twitterapi.io only)
USE_PAGINATION = False     # Fix #2: Twikit can't paginate → False uses fetch_tweets()
                           # True uses paginator with twitterapi.io cursor

# ── Retry / delay settings ────────────────────────────────────────────────────
MAX_RETRIES   = 3
RETRY_DELAY   = 3          # seconds between retries
RATE_LIMIT_DELAY = 10      # seconds to wait on 429
PAGE_DELAY    = 5          # seconds between pagination pages
QUERY_DELAY   = 5          # seconds between queries

# ── Scheduler settings ────────────────────────────────────────────────────────
SCHEDULER_ENABLED    = True   # set False to run just once
RUN_INTERVAL_HOURS   = 2      # hours between each full pipeline run
MAX_RUNS             = 0      # 0 = run forever, N = stop after N runs

# ── File paths ────────────────────────────────────────────────────────────────
QUERIES_FILE     = "queries.txt"
COOKIES_FILE     = "twikit_cookies.json"
RAW_DATA_DIR     = "data/raw"
PROCESSED_DIR    = "data/processed"
NLP_DIR          = "data/nlp"

# ── Credit warning settings ───────────────────────────────────────────────────
MIN_CREDITS_THRESHOLD = 500   # warn if credits fall below this
STOP_ON_LOW_CREDITS   = True  # stop pipeline if below threshold
RETRY_CODES = {429, 500, 502, 503}