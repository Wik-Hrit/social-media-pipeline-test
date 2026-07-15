"""
twikit_client.py — Cookie-based Twitter client (no pagination).
Fix #4: Cookie fail → delete → login immediately → retry once (not next run)
Fix #5: Credential validation at startup
Fix #6: Settings from config.py
Fix #7: print() replaced with log.*()
"""

import asyncio
import os
import logging
from dotenv import load_dotenv
from config import COOKIES_FILE

load_dotenv()
log = logging.getLogger(__name__)

try:
    from twikit import Client
    TWIKIT_AVAILABLE = True
except ImportError:
    TWIKIT_AVAILABLE = False
    log.warning("[twikit] Not installed. Run: pip install twikit")

TWITTER_USERNAME = os.getenv("TWITTER_USERNAME")
TWITTER_EMAIL    = os.getenv("TWITTER_EMAIL")
TWITTER_PASSWORD = os.getenv("TWITTER_PASSWORD")

# Fix #5 — credential validation at startup
if TWIKIT_AVAILABLE and not all([TWITTER_USERNAME, TWITTER_EMAIL, TWITTER_PASSWORD]):
    log.error("[twikit] Credentials missing in .env (TWITTER_USERNAME / TWITTER_EMAIL / TWITTER_PASSWORD)")

_client = None
_loop: asyncio.AbstractEventLoop | None = None   # Fix 2: persistent loop


async def _login_fresh(client):
    """Login fresh and save cookies."""
    log.info("[twikit] Logging in (first-time setup)...")
    await client.login(
        auth_info_1=TWITTER_USERNAME,
        auth_info_2=TWITTER_EMAIL,
        password=TWITTER_PASSWORD,
    )
    client.save_cookies(COOKIES_FILE)
    log.info(f"[twikit] Cookies saved to {COOKIES_FILE}")
    return client


async def _get_client():
    global _client
    if _client is not None:
        return _client

    client = Client(language="en-US")

    if os.path.exists(COOKIES_FILE):
        client.load_cookies(COOKIES_FILE)
        log.info(f"[twikit] Loaded cookies from {COOKIES_FILE}")
    else:
        client = await _login_fresh(client)

    _client = client
    return _client


async def _fetch(query, query_type="Latest", count=20):
    if not TWIKIT_AVAILABLE:
        log.error("[twikit] Not installed.")
        return False, {}

    # Fix #4 — try once, if cookie fails: delete → re-login immediately → retry once
    for attempt in range(2):
        try:
            client = await _get_client()
            product    = "Latest" if query_type.lower() == "latest" else "Top"
            raw_tweets = await client.search_tweet(query, product=product, count=count)

            tweets = []
            for t in raw_tweets:
                # Fix 1: proper retweetedTweet detection
                rt = getattr(t, "retweeted_tweet", None)
                retweeted_id = str(rt.id) if rt else None

                # Fix 12: viewCount — None means unknown, not zero
                view_count = getattr(t, "view_count", None) or None

                # Fix 13: extract hashtags from Twikit object or regex fallback
                import re as _re
                twikit_tags = []
                if hasattr(t, "hashtags") and t.hashtags:
                    twikit_tags = [{"text": h} for h in t.hashtags]
                elif t.text:
                    twikit_tags = [{"text": m} for m in _re.findall(r"#(\w+)", t.text)]

                tweets.append({
                    "id":           str(t.id),
                    "text":         t.text,
                    "createdAt":    str(t.created_at),
                    "author": {
                        "userName": t.user.screen_name if t.user else None,
                        "followers": t.user.followers_count if t.user else None,
                    },
                    "lang":         getattr(t, "lang", None),
                    "retweetCount": getattr(t, "retweet_count", 0),
                    "likeCount":    getattr(t, "favorite_count", 0),
                    "replyCount":   getattr(t, "reply_count", 0),
                    "viewCount":    view_count,           # Fix 12
                    "isReply":      getattr(t, "in_reply_to_tweet_id", None) is not None,
                    "retweetedTweet": retweeted_id,       # Fix 1
                    "twitterUrl":   f"https://twitter.com/i/web/status/{t.id}",
                    "entities":     {"hashtags": twikit_tags},  # Fix 13
                    "_source":      "twikit",
                })

            log.info(f"[twikit] ✓ {len(tweets)} tweets fetched")
            return True, {"tweets": tweets, "count": len(tweets)}

        except Exception as e:
            is_cookie_error = any(kw in str(e) for kw in ["expire", "auth", "KEY_BYTE", "cookie", "login"])

            if is_cookie_error and attempt == 0:
                # Fix #4 — delete cookie and re-login IMMEDIATELY (not next run)
                log.warning(f"[twikit] Cookie expired — deleting and re-logging in immediately...")
                if os.path.exists(COOKIES_FILE):
                    os.remove(COOKIES_FILE)
                global _client
                _client = None

                # Re-login fresh right now
                try:
                    fresh_client = Client(language="en-US")
                    await _login_fresh(fresh_client)
                    _client = fresh_client
                    log.info("[twikit] Re-login successful — retrying fetch...")
                    continue   # retry the fetch with fresh cookies
                except Exception as login_err:
                    log.error(f"[twikit] Re-login failed: {login_err}")
                    return False, {}
            else:
                log.error(f"[twikit] Fetch failed: {e}")
                return False, {}

    return False, {}


def get_twikit(query, query_type="Latest", count=20):
    global _loop
    if _loop is None or _loop.is_closed():
        _loop = asyncio.new_event_loop()
        asyncio.set_event_loop(_loop)
    return _loop.run_until_complete(_fetch(query, query_type, count))