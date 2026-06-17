import time
from twitter_client import get

def fetch_all_pages(query, query_type="Latest", max_pages=5):
    all_tweets = []
    next_cursor = None
    page = 1

    while page <= max_pages:
        print(f"  Fetching page {page}...")

        params = {
            "query": query,
            "queryType": query_type,
        }

        if next_cursor:
            params["cursor"] = next_cursor

        success, data = get("/twitter/tweet/advanced_search", params)

        if not success or not data:
            print(f"  ✗ Failed on page {page}")
            break

        tweets = data.get("tweets", [])
        if not tweets:
            print(f"  No more tweets found")
            break

        all_tweets.extend(tweets)
        print(f"  ✓ Page {page}: {len(tweets)} tweets (total: {len(all_tweets)})")

        next_cursor = data.get("next_cursor") or data.get("nextCursor")

        if not next_cursor:
            print(f"  No more pages available")
            break

        page += 1
        time.sleep(5)  # wait between pages

    print(f"  Total tweets collected: {len(all_tweets)}")
    return all_tweets