"""
fetch_tweets.py — Single-page fetch with Twikit primary, twitterapi.io fallback.
Used when USE_PAGINATION = False (Twikit mode).
Fix #3: metadata apisource → apisources (list)
Fix #6: settings from config.py
Fix #7: print() replaced with log.*()
"""

import logging
from twikit_client import get_twikit
from twitter_client import get
from config import COUNT, QUERY_TYPE

log = logging.getLogger(__name__)

_FALLBACK_CODES = {429, 402, 403}


def fetch_tweets(query, query_type=QUERY_TYPE, count=COUNT):
    log.info(f"Fetching tweets for: '{query}'")

    # ── Primary: Twikit (cookie-based, no pagination) ─────────────────────────
    success, data = get_twikit(query, query_type, count)

    if success:
        tweets = data.get("tweets", [])
        # Fix #3 — apisource → apisources
        data["apisources"] = ["twikit"]
        log.info(f"  ✓ {len(tweets)} tweets fetched via twikit")
        return True, data, "twikit"

    # ── Fallback: twitterapi.io ───────────────────────────────────────────────
    log.warning("  Twikit failed — switching to twitterapi.io fallback...")

    params = {
        "query":     query,
        "queryType": query_type,
        "count":     count,
    }

    success, data = get("/twitter/tweet/advanced_search", params)

    if success:
        tweets = data.get("tweets", [])
        # Fix #3 — apisources as list
        data["apisources"] = ["twitterapi.io"]
        log.info(f"  ✓ {len(tweets)} tweets fetched via twitterapi.io fallback")
        return True, data, "twitterapi.io"

    log.error(f"  Both sources failed for '{query}'")
    return False, None, None