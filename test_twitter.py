import requests
import json
import os
from dotenv import load_dotenv

load_dotenv()
API_KEY = os.getenv("TWITTER_API_KEY")

headers = {"X-API-Key": API_KEY}

url = "https://api.twitterapi.io/twitter/tweet/advanced_search"
params = {
    "query": "Manipur flood",
    "queryType": "Latest"
}

response = requests.get(url, headers=headers, params=params)
data = response.json()

tweets = []
for tweet in data.get("tweets", []):
    tweets.append({
        "id": tweet.get("id"),
        "text": tweet.get("text"),
        "createdAt": tweet.get("createdAt"),
        "author": tweet.get("author", {}).get("userName"),
        "retweetCount": tweet.get("retweetCount"),
        "likeCount": tweet.get("likeCount"),
        "url": tweet.get("twitterUrl")
    })

print(f"Total tweets fetched: {len(tweets)}")

with open("manipur_flood_tweets.json", "w", encoding="utf-8") as f:
    json.dump(tweets, f, ensure_ascii=False, indent=2)

print("Saved to manipur_flood_tweets.json")