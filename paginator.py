"""
paginator.py — Cursor-based pagination using twitterapi.io.
Fix #1: Twikit cannot paginate → only used when USE_PAGINATION=False (in main.py)
Fix #2: twitterapi.io supports cursor → use it for proper pagination
Fix #7: print() replaced with log.*()
Fix #8: page number tracked and returned in metadata
"""

import time
import logging
from twitter_client import get
from config import COUNT, PAGE_DELAY

log = logging.getLogger(__name__)


def fetch_all_pages(query, query_type="Latest", max_pages=3):
    """
    Paginate using twitterapi.io cursor.
    Twikit is NOT used here — it cannot paginate (Fix #1 & #2).
    """
    all_tweets = []
    seen_ids   = set()
    source     = "twitterapi.io"
    cursor     = None
    page       = 1

    while page <= max_pages:
        log.info(f"  Fetching page {page}...")

        params = {
            "query":     query,
            "queryType": query_type,
            "count":     COUNT,
        }
        if cursor:
            params["cursor"] = cursor   # Fix #2 — use cursor for real pagination

        success, data = get("/twitter/tweet/advanced_search", params)

        if not success or not data:
            log.error(f"  twitterapi.io failed on page {page}")
            break

        tweets = data.get("tweets", [])
        if not tweets:
            log.info(f"  No more tweets found on page {page}")
            break

        # Deduplicate across pages
        new_tweets = []
        for t in tweets:
            tid = t.get("id") or t.get("id_str")
            if tid and tid not in seen_ids:
                seen_ids.add(tid)
                t["_source"]  = source
                t["_page_no"] = page     # Fix #8 — store page number per tweet
                new_tweets.append(t)

        all_tweets.extend(new_tweets)
        log.info(f"  ✓ Page {page}: {len(new_tweets)} new tweets (total: {len(all_tweets)})")

        # Fix #2 — advance cursor for next page
        cursor = data.get("next_cursor") or data.get("cursor") or data.get("nextCursor")
        if not cursor:
            log.info("  No next cursor — pagination complete")
            break

        page += 1
        if page <= max_pages:
            time.sleep(PAGE_DELAY)

    log.info(f"Total tweets collected: {len(all_tweets)}")
    return all_tweets, source