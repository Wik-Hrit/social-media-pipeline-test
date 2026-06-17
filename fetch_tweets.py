"""
fetch_tweets.py
Primary fetch via twitterapi.io; automatic Twikit fallback on 429 / quota errors.
Return signature unchanged: (success: bool, data: dict)
"""

from twitter_client import get
from twikit_client import get_twikit

# HTTP / API error codes that should trigger the fallback
_FALLBACK_CODES = {429, 402, 403}


def _primary_failed_with_quota(data: dict | None) -> bool:
    """Return True if the primary response signals a rate-limit / quota error."""
    if data is None:
        return False
    status = data.get("status") or data.get("code") or data.get("error_code")
    if isinstance(status, int) and status in _FALLBACK_CODES:
        return True
    # Some APIs embed the status inside a nested 'error' key
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

    # ── Primary: twitterapi.io ────────────────────────────────────────────────
    success, data = get("/twitter/tweet/advanced_search", params)

    if success:
        tweets = data.get("tweets", [])
        print(f"  ✓ {len(tweets)} tweets fetched")
        return success, data

    # ── Fallback decision ─────────────────────────────────────────────────────
    use_fallback = _primary_failed_with_quota(data)

    if not use_fallback:
        # Non-quota failure (bad query, network blip, etc.) — don't waste Twikit
        print(f"  ✗ Failed to fetch tweets for '{query}'")
        return False, None

    # ── Fallback: Twikit ─────────────────────────────────────────────────────
    print("  ⚠ twitterapi.io quota/rate-limit hit — switching to Twikit fallback...")
    success, data = get_twikit(query, query_type, count)

    if success:
        return success, data

    print(f"  ✗ Fallback also failed for '{query}'")
    return False, None