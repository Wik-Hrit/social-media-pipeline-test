"""
twikit_client.py — Cookie-based Twitter fallback client.
Fix #5: cookie expiration handled — deletes stale cookie file and re-logins.
Fix #1: schema normalized to match twitterapi.io output format.
"""

import asyncio
import os
import logging
from dotenv import load_dotenv

load_dotenv()
log = logging.getLogger(__name__)

try:
    from twikit import Client
    TWIKIT_AVAILABLE = True
except ImportError:
    TWIKIT_AVAILABLE = False

TWITTER_USERNAME = os.getenv("TWITTER_USERNAME")
TWITTER_EMAIL    = os.getenv("TWITTER_EMAIL")
TWITTER_PASSWORD = os.getenv("TWITTER_PASSWORD")
COOKIES_FILE     = os.getenv("TWIKIT_COOKIES_FILE", "twikit_cookies.json")

# Fix #11 — credential validation
if TWIKIT_AVAILABLE and not all([TWITTER_USERNAME, TWITTER_EMAIL, TWITTER_PASSWORD]):
    log.error("Twikit credentials missing in .env (TWITTER_USERNAME / TWITTER_EMAIL / TWITTER_PASSWORD)")

_client = None


async def _get_client():
    global _client
    if _client is not None:
        return _client

    client = Client(language="en-US")

    if os.path.exists(COOKIES_FILE):
        client.load_cookies(COOKIES_FILE)
        log.info(f"[twikit] Loaded cookies from {COOKIES_FILE}")
    else:
        log.info("[twikit] Logging in (first-time setup)...")
        await client.login(
            auth_info_1=TWITTER_USERNAME,
            auth_info_2=TWITTER_EMAIL,
            password=TWITTER_PASSWORD,
        )
        client.save_cookies(COOKIES_FILE)
        log.info(f"[twikit] Cookies saved to {COOKIES_FILE}")

    _client = client
    return _client


async def _fetch(query, query_type="Latest", count=20):
    if not TWIKIT_AVAILABLE:
        log.error("[twikit] Not installed. Run: pip install twikit")
        return False, {}

    try:
        client = await _get_client()
        product = "Latest" if query_type.lower() == "latest" else "Top"
        raw_tweets = await client.search_tweet(query, product=product, count=count)

        tweets = []
        for t in raw_tweets:
            # Fix #1 — normalize schema to match twitterapi.io
            tweets.append({
                "id":              str(t.id),
                "text":            t.text,
                "createdAt":       str(t.created_at),
                "author": {
                    "userName":    t.user.screen_name if t.user else None,
                    "followers":   t.user.followers_count if t.user else None,
                },
                "lang":            getattr(t, "lang", None),
                "retweetCount":    getattr(t, "retweet_count", 0),
                "likeCount":       getattr(t, "favorite_count", 0),
                "replyCount":      getattr(t, "reply_count", 0),
                "viewCount":       getattr(t, "view_count", 0),
                "isReply":         getattr(t, "in_reply_to_tweet_id", None) is not None,
                "retweetedTweet":  None,
                "twitterUrl":      f"https://twitter.com/i/web/status/{t.id}",
                "entities":        {"hashtags": []},
                "_source":         "twikit",
            })

        log.info(f"[twikit] ✓ {len(tweets)} tweets fetched")
        return True, {"tweets": tweets, "count": len(tweets)}

    except Exception as e:
        # Fix #5 — if cookie expired, delete and signal re-login next time
        if "expire" in str(e).lower() or "auth" in str(e).lower() or "KEY_BYTE" in str(e):
            log.warning(f"[twikit] Cookie may be expired — deleting {COOKIES_FILE} for re-login next run")
            if os.path.exists(COOKIES_FILE):
                os.remove(COOKIES_FILE)
            global _client
            _client = None
        log.error(f"[twikit] Fetch failed: {e}")
        return False, {}


def get_twikit(query, query_type="Latest", count=20):
    return asyncio.run(_fetch(query, query_type, count))