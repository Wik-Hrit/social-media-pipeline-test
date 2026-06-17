from twitter_client import get

def fetch_tweets(query, query_type="Latest", count=20):
    print(f"Fetching tweets for: '{query}'")
    
    params = {
        "query": query,
        "queryType": query_type,
        "count": count
    }
    
    success, data = get("/twitter/tweet/advanced_search", params)
    
    if success:
        tweets = data.get("tweets", [])
        print(f"  ✓ {len(tweets)} tweets fetched")
        return success, data
    else:
        print(f"  ✗ Failed to fetch tweets for '{query}'")
        return False, None