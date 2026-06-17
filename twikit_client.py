"""
twikit_client.py
Fallback Twitter client using Twikit (cookie-based auth).
Mirrors the interface of twitter_client.py:
    get_twikit(query, query_type, count) -> (success: bool, data: dict)
"""

import asyncio
import os
from dotenv import load_dotenv
from error_handler import handle_response

load_dotenv()

# ── Twikit lazy import (optional dependency) ──────────────────────────────────
try:
    from twikit import Client
    TWIKIT_AVAILABLE = True
except ImportError:
    TWIKIT_AVAILABLE = False

# ── Credentials (add these to your .env) ─────────────────────────────────────
TWITTER_USERNAME = os.getenv("TWITTER_USERNAME")
TWITTER_EMAIL    = os.getenv("TWITTER_EMAIL")
TWITTER_PASSWORD = os.getenv("TWITTER_PASSWORD")
COOKIES_FILE     = os.getenv("TWIKIT_COOKIES_FILE", "twikit_cookies.json")

_client: "Client | None" = None  # module-level singleton


async def _get_client() -> "Client":
    """Return authenticated Twikit client (login once, reuse cookies)."""
    global _client
    if _client is not None:
        return _client

    client = Client(language="en-US")

    if os.path.exists(COOKIES_FILE):
        # Reuse saved cookies — avoids repeated login
        client.load_cookies(COOKIES_FILE)
        print(f"[twikit] Loaded cookies from {COOKIES_FILE}")
    else:
        print("[twikit] Logging in (first-time setup)...")
        await client.login(
            auth_info_1=TWITTER_USERNAME,
            auth_info_2=TWITTER_EMAIL,
            password=TWITTER_PASSWORD,
        )
        client.save_cookies(COOKIES_FILE)
        print(f"[twikit] Cookies saved to {COOKIES_FILE}")

    _client = client
    return _client


async def _fetch(query: str, query_type: str = "Latest", count: int = 20) -> tuple[bool, dict]:
    """Core async fetch — called by the sync wrapper below."""
    if not TWIKIT_AVAILABLE:
        print("[twikit] ✗ twikit not installed. Run: pip install twikit")
        return False, {}

    if not all([TWITTER_USERNAME, TWITTER_EMAIL, TWITTER_PASSWORD]):
        print("[twikit] ✗ Missing credentials in .env (TWITTER_USERNAME / TWITTER_EMAIL / TWITTER_PASSWORD)")
        return False, {}

    try:
        client = await _get_client()
        product = "Latest" if query_type.lower() == "latest" else "Top"

        raw_tweets = await client.search_tweet(query, product=product, count=count)

        tweets = []
        for t in raw_tweets:
            tweets.append({
                "id":         str(t.id),
                "text":       t.text,
                "created_at": str(t.created_at),
                "author_id":  str(t.user.id) if t.user else None,
                "author":     t.user.screen_name if t.user else None,
                "lang":       getattr(t, "lang", None),
                "retweet_count":  getattr(t, "retweet_count", 0),
                "favorite_count": getattr(t, "favorite_count", 0),
                "source": "twikit",
            })

        data = {"tweets": tweets, "count": len(tweets)}
        print(f"[twikit] ✓ {len(tweets)} tweets fetched (fallback)")
        return True, data

    except Exception as e:
        print(f"[twikit] ✗ Fetch failed: {e}")
        return False, {}


def get_twikit(query: str, query_type: str = "Latest", count: int = 20) -> tuple[bool, dict]:
    """
    Sync wrapper — drop-in replacement for twitter_client.get().
    Returns (success, data) matching the primary client's format.
    """
    return asyncio.run(_fetch(query, query_type, count))