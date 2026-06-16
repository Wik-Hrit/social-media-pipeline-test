import requests
import json
import os
from dotenv import load_dotenv
from datetime import datetime

load_dotenv()
API_KEY = os.getenv("TWITTER_API_KEY")
headers = {"X-API-Key": API_KEY}

# ============================================================
# ADD YOUR QUERIES HERE
# ============================================================
queries = [
    "Manipur flood 2026",
    "#DelhiHeatwave",
    "India election results",
    "Mumbai monsoon 2026",
    "#Kashmir",
    "Cyclone India",
    "NEET exam 2026",
    "IPL 2026"
]

def fetch_tweets(query, query_type="Latest"):
    url = "https://api.twitterapi.io/twitter/tweet/advanced_search"
    params = {
        "query": query,
        "queryType": query_type
    }
    response = requests.get(url, headers=headers, params=params)
    return response.json()

def save_tweets(query, data):
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
    
    # Timestamp in filename
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    filename = f"{query.replace(' ', '_')}_{timestamp}.json"
    
    # Save in output folder
    os.makedirs("output", exist_ok=True)
    filepath = os.path.join("output", filename)
    
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump({
            "query": query,
            "fetchedAt": datetime.now().isoformat(),
            "totalTweets": len(tweets),
            "tweets": tweets
        }, f, ensure_ascii=False, indent=2)
    
    return filepath, len(tweets)

# ============================================================
# MAIN
# ============================================================
print(f"Starting tweet collection at {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")

for query in queries:
    print(f"Fetching: '{query}'...")
    data = fetch_tweets(query)
    filepath, count = save_tweets(query, data)
    print(f"  ✓ {count} tweets saved → {filepath}")

print(f"\nDone! All files saved in /output folder")