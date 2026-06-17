# Social Media Acquisition Pipeline
Twitter data collection pipeline for the Multimodal Broadcast Analytics System, IIT Guwahati.

## Project Structure
social-media-pipeline-test/

├── twitter_client.py      # API connection layer

├── fetch_tweets.py        # fetch_tweets(query, query_type, count)

├── save_raw.py            # saves full raw API response

├── save_processed.py      # saves clean structured data

├── error_handler.py       # handles all HTTP status codes

├── paginator.py           # multi-page tweet collection

├── filenamegen.py         # timestamped filename generation

├── main.py                # pipeline entry point

├── queries.txt            # add/remove queries here

├── data/

│   ├── raw/               # raw API responses

│   └── processed/         # clean structured JSON

└── .env                   # API keys (not committed)
## How To Run
```bash
# activate venv
venv\Scripts\activate

# install dependencies
pip install -r requirements.txt

# add queries to queries.txt, then run
python main.py
```

## Configuration
In `main.py`:
```python
QUERY_TYPE = "Latest"  # or "Top"
COUNT = 20             # tweets per page
USE_PAGINATION = True  # False for single page only
```

## API Options Evaluated

### twitterapi.io (current)
Unofficial wrapper around X's internal API. 100K free credits on signup, then $0.15/1000 tweets. No account login needed. Reliable for research-scale collection. Pagination works on free tier with rate limiting — needs 5s delay between pages.

**Limitations:** Free credits deplete with heavy testing. Pagination hits 429 if requests are too fast.

### Twikit
Pure Python, completely free, no API key needed. Uses actual Twitter account credentials (username + email + password) to authenticate. Actively maintained as of 2026.

**Honest assessment:** Works, but X changes internal endpoints every 2-4 weeks causing breakage. Logged-in account risks suspension from aggressive scraping. Viable as a free fallback for low-volume use but not recommended for production pipelines.

### Twscrape
No meaningful updates in ~11 months. Likely broken against current X endpoints. Not recommended.

### Official X API
Free tier is write-only — cannot search or read tweets. Basic plan starts at $200/month for 10K tweets. Not viable for research use without budget approval.

## Error Handling
| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Continue |
| 401 | Invalid API key | Stop |
| 402 | Payment required / credits exhausted | Stop |
| 403 | Access denied | Stop |
| 404 | Wrong endpoint | Stop |
| 429 | Rate limit exceeded | Wait and retry |
| 500 | Server error | Stop |

## Output Format
Each query produces two files:

**Raw** (`data/raw/query_timestamp.json`) — complete API response, nothing stripped.

**Processed** (`data/processed/query_timestamp.json`):
```json
{
  "metadata": {
    "query": "Manipur flood",
    "fetchedAt": "2026-06-17T07:45:52",
    "apiSource": "twitterapi.io",
    "tweetCount": 60
  },
  "tweets": [
    {
      "id": "...",
      "text": "...",
      "createdAt": "...",
      "author": "...",
      "authorFollowers": 4521,
      "retweetCount": 3,
      "likeCount": 4,
      "replyCount": 0,
      "viewCount": 500,
      "lang": "en",
      "url": "https://twitter.com/...",
      "isReply": false,
      "isRetweet": false,
      "hashtags": ["Manipur", "flood"]
    }
  ]
}
```