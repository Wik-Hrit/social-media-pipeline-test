import time
import logging
from twikit_client import get_twikit
from twitter_client import get

log = logging.getLogger(__name__)

def fetch_all_pages(query, query_type="Latest", max_pages=3):
    all_tweets = []
    seen_ids   = set()        # Fix #3 — cursor overlap deduplication
    source     = "twitterapi.io"
    page       = 1
    count      = 20           # Fix #6 — count now passed explicitly

    while page <= max_pages:
        log.info(f"  Fetching page {page}...")

        # Primary: Twikit
        success, data = get_twikit(query, query_type, count=count)

        if success:
            source = "twikit"
        else:
            # Fallback: twitterapi.io
            log.warning(f"  Twikit failed on page {page} — trying twitterapi.io...")
            params = {"query": query, "queryType": query_type, "count": count}
            success, data = get("/twitter/tweet/advanced_search", params)
            if success:
                source = "twitterapi.io"

        if not success or not data:
            log.error(f"  Both sources failed on page {page}")
            break

        tweets = data.get("tweets", [])
        if not tweets:
            log.info(f"  No more tweets found on page {page}")
            break

        # Fix #3 — deduplicate by id across pages
        new_tweets = []
        for t in tweets:
            tid = t.get("id") or t.get("id_str")
            if tid and tid not in seen_ids:
                seen_ids.add(tid)
                # Fix #8 — store source per tweet
                t["_source"] = source
                new_tweets.append(t)

        all_tweets.extend(new_tweets)
        log.info(f"  ✓ Page {page}: {len(new_tweets)} new tweets (total: {len(all_tweets)})")

        page += 1
        if page <= max_pages:
            time.sleep(5)

    log.info(f"Total tweets collected: {len(all_tweets)}")
    return all_tweets, source   # Fix #2 — return source