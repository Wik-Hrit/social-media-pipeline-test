from twitter_client import get
from twikit_client import get_twikit

_FALLBACK_CODES = {429, 402, 403}


def _primary_failed_with_quota(data):
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

    params = {
        "query":     query,
        "queryType": query_type,
        "count":     count,
    }

    # Primary: twitterapi.io
    success, data = get("/twitter/tweet/advanced_search", params)

    if success:
        tweets = data.get("tweets", [])
        print(f"  ✓ {len(tweets)} tweets fetched")
        return True, data, "twitterapi.io"

    # Fallback decision
    if not _primary_failed_with_quota(data):
        print(f"  ✗ Failed to fetch tweets for '{query}'")
        return False, None, None

    # Fallback: Twikit
    print("  ⚠ Quota/rate-limit hit — switching to Twikit fallback...")
    success, data = get_twikit(query, query_type, count)

    if success:
        return True, data, "twikit"

    print(f"  ✗ Fallback also failed for '{query}'")
    return False, None, None