from twikit_client import get_twikit
from twitter_client import get

_FALLBACK_CODES = {429, 402, 403}


def _failed_with_quota(data):
    if data is None:
        return False
    status = data.get("status") or data.get("code") or data.get("error_code")
    if isinstance(status, int) and status in _FALLBACK_CODES:
        return True
    error = data.get("error", {})
    if isinstance(error, dict):
        code = error.get("code") or error.get("status")
        if isinstance(code, int) and code in _FALLBACK_CODES:
            return True
    return False


def fetch_tweets(query, query_type="Latest", count=20):
    print(f"Fetching tweets for: '{query}'")

    # ── Primary: Twikit (cookie-based) ───────────────────────────────
    success, data = get_twikit(query, query_type, count)

    if success:
        tweets = data.get("tweets", [])
        print(f"  ✓ {len(tweets)} tweets fetched")
        return True, data, "twikit"

    # ── Fallback: twitterapi.io ───────────────────────────────────────
    print("  ⚠ Twikit failed — switching to twitterapi.io fallback...")

    params = {
        "query":     query,
        "queryType": query_type,
        "count":     count,
    }

    success, data = get("/twitter/tweet/advanced_search", params)

    if success:
        tweets = data.get("tweets", [])
        print(f"  ✓ {len(tweets)} tweets fetched (twitterapi.io fallback)")
        return True, data, "twitterapi.io"

    print(f"  ✗ Both sources failed for '{query}'")
    return False, None, None