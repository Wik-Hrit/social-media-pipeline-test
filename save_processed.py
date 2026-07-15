import json
import os
import logging
from filenamegen import generate_filename
from datetime import datetime

log = logging.getLogger(__name__)

def save_processed(query, data, source="twitterapi.io"):
    tweets = []
    meta_extra = data.get("meta") or data.get("metadata") or {}  # Fix 10: pipeline metadata

    for tweet in data.get("tweets", []):
        # Fix #8 — source per tweet (use _source if set by paginator)
        tweet_source = tweet.get("_source", source)

        # Fix 4: author can be dict or string depending on API source
        author_raw = tweet.get("author", {})
        if isinstance(author_raw, dict):
            author_name = author_raw.get("userName")
            author_flw  = author_raw.get("followers")
        else:
            author_name = author_raw
            author_flw  = None

        tweets.append({
            "id":              tweet.get("id"),
            "text":            tweet.get("text"),
            "createdAt":       tweet.get("createdAt"),
            "author":          author_name,        # Fix 4
            "authorFollowers": author_flw,         # Fix 4
            "retweetCount":    tweet.get("retweetCount"),
            "likeCount":       tweet.get("likeCount"),
            "replyCount":      tweet.get("replyCount"),
            "viewCount":       tweet.get("viewCount"),
            "bookmarkCount":   tweet.get("bookmarkCount"),  # Fix 11
            "lang":            tweet.get("lang"),
            "url":             tweet.get("twitterUrl"),
            "isReply":         tweet.get("isReply"),
            "isRetweet":       tweet.get("retweetedTweet") is not None,
            "hashtags": [
                h.get("text")
                for h in tweet.get("entities", {}).get("hashtags", [])
            ],
            "source":          tweet_source,
        })

    processed = {
        "metadata": {
            "query":            query,
            "fetchedAt":        datetime.now().isoformat(),
            "apiSource":        source,
            "tweetCount":       len(tweets),
            "pipeline_version": meta_extra.get("pipeline_version", ""),   # Fix 10
            "query_type":       meta_extra.get("query_type", ""),          # Fix 10
            "use_pagination":   meta_extra.get("use_pagination", False),   # Fix 10
            "run_number":       meta_extra.get("run_number", 1),           # Fix 10
            "apisources":       data.get("apisources", [source]),          # Fix 10
        },
        "tweets": tweets
    }

    filepath = generate_filename(query, folder="processed")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    # Fix #7 — exception handling around json.dump
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(processed, f, ensure_ascii=False, indent=2)
        log.info(f"  ✓ Processed data saved → {filepath}")
    except Exception as e:
        log.error(f"  ✗ Failed to save processed data: {e}")
        return None

    return filepath