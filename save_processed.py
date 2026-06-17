import json
import os
from filenamegen import generate_filename
from datetime import datetime

def save_processed(query, data):
    tweets = []
    
    for tweet in data.get("tweets", []):
        tweets.append({
            "id": tweet.get("id"),
            "text": tweet.get("text"),
            "createdAt": tweet.get("createdAt"),
            "author": tweet.get("author", {}).get("userName"),
            "authorFollowers": tweet.get("author", {}).get("followers"),
            "retweetCount": tweet.get("retweetCount"),
            "likeCount": tweet.get("likeCount"),
            "replyCount": tweet.get("replyCount"),
            "viewCount": tweet.get("viewCount"),
            "lang": tweet.get("lang"),
            "url": tweet.get("twitterUrl"),
            "isReply": tweet.get("isReply"),
            "isRetweet": tweet.get("retweetedTweet") is not None,
            "hashtags": [
                h.get("text")
                for h in tweet.get("entities", {}).get("hashtags", [])
            ]
        })

    # Metadata — Problem 4 solved
    processed = {
        "metadata": {
            "query": query,
            "fetchedAt": datetime.now().isoformat(),
            "apiSource": "twitterapi.io",
            "tweetCount": len(tweets)
        },
        "tweets": tweets
    }

    filepath = generate_filename(query, folder="processed")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(processed, f, ensure_ascii=False, indent=2)

    print(f"  ✓ Processed data saved → {filepath}")
    return filepath