import json
import os
import logging
from filenamegen import generate_filename
from datetime import datetime

log = logging.getLogger(__name__)

def save_processed(query, data, source="twitterapi.io"):
    tweets = []

    for tweet in data.get("tweets", []):
        # Fix #8 — source per tweet (use _source if set by paginator)
        tweet_source = tweet.get("_source", source)

        tweets.append({
            "id":              tweet.get("id"),
            "text":            tweet.get("text"),
            "createdAt":       tweet.get("createdAt"),
            "author":          tweet.get("author", {}).get("userName"),
            "authorFollowers": tweet.get("author", {}).get("followers"),
            "retweetCount":    tweet.get("retweetCount"),
            "likeCount":       tweet.get("likeCount"),
            "replyCount":      tweet.get("replyCount"),
            "viewCount":       tweet.get("viewCount"),
            "lang":            tweet.get("lang"),
            "url":             tweet.get("twitterUrl"),
            "isReply":         tweet.get("isReply"),
            "isRetweet":       tweet.get("retweetedTweet") is not None,
            "hashtags": [
                h.get("text")
                for h in tweet.get("entities", {}).get("hashtags", [])
            ],
            "source":          tweet_source,   # Fix #8
        })

    processed = {
        "metadata": {
            "query":      query,
            "fetchedAt":  datetime.now().isoformat(),
            "apiSource":  source,
            "tweetCount": len(tweets)
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