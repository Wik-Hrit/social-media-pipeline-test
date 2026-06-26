# Social Media Acquisition Pipeline

Twitter data collection and NLP preprocessing pipeline for the Multimodal Broadcast Analytics System, IIT Guwahati.

---

## Project Structure

```
social-media-pipeline-test/
├── twitter_client.py      # API connection layer (retry, timeout, exception handling)
├── twikit_client.py       # Cookie-based fallback client (auto-activates on quota errors)
├── fetch_tweets.py        # fetch_tweets(query, query_type, count) → (success, data, source)
├── save_raw.py            # saves full raw API response
├── save_processed.py      # saves clean structured data with source tracking
├── error_handler.py       # handles all HTTP status codes
├── paginator.py           # multi-page tweet collection with deduplication
├── filenamegen.py         # timestamped filename generation
├── preprocess.py          # NLP preprocessing pipeline (cleaning → filtering → NLP enrichment)
├── export_csv.py          # exports data/nlp/ to per-topic CSVs in data/csv/
├── main.py                # pipeline entry point
├── queries.txt            # add/remove queries here (duplicates auto-removed)
├── data/
│   ├── raw/               # raw API responses
│   ├── processed/         # clean structured JSON with metadata
│   ├── nlp/               # NLP-enriched output (tokens, sentiment, entities, keywords)
│   └── csv/               # per-topic CSV exports (one file per query slug)
└── .env                   # API keys and credentials (not committed)
```

---

## How To Run

```bash
# activate venv
venv\Scripts\activate

# install dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm
python -m textblob.download_corpora

# add queries to queries.txt, then run acquisition
python main.py

# run NLP preprocessing on collected data
python preprocess.py

# export to CSV for review
python export_csv.py
```

---

## Configuration

In `main.py`:

```python
QUERY_TYPE     = "Latest"  # or "Top"
COUNT          = 20        # tweets per page
USE_PAGINATION = True      # False for single page only
```

In `paginator.py`:

```python
max_pages = 3  # 3 pages × 20 tweets = 60 tweets per query
```

---

## Pipeline Flow

```
queries.txt
    ↓
main.py  (orchestrator)
    ↓
paginator.py  (multi-page collection)
    ↓
fetch_tweets.py
    ├── Primary:  twikit_client.py  (cookie-based, free)
    └── Fallback: twitter_client.py → twitterapi.io  (on quota/rate-limit errors)
    ↓
error_handler.py  (status code handling, retry logic)
    ↓
save_raw.py      →  data/raw/
save_processed.py →  data/processed/
    ↓
preprocess.py    →  data/nlp/
    ↓
export_csv.py    →  data/csv/
```

---

## Fallback Logic

The pipeline uses a two-source strategy:

- **Primary:** Twikit (cookie-based, completely free, no API key needed)
- **Fallback:** twitterapi.io (activates automatically on 429 / 402 / 403 errors)

Source is tracked per tweet and stored in the `source` field of processed output and in `apiSource` in the metadata block.

To set up Twikit, add to `.env`:

```
TWITTER_USERNAME=your_twitter_handle
TWITTER_EMAIL=your@email.com
TWITTER_PASSWORD=yourpassword
TWIKIT_COOKIES_FILE=twikit_cookies.json
```

First run logs in and saves `twikit_cookies.json`. Subsequent runs reuse cookies silently. If cookies expire, the file is deleted automatically and re-login happens on the next run.

> Use a dedicated/burner Twitter account for the pipeline — not your personal account.

---

## API Options Evaluated

### twitterapi.io (fallback)
Unofficial wrapper around X's internal API. 100K free credits on signup, then $0.15/1000 tweets. No account login needed. Reliable for research-scale collection.

**Limitations:** Free credits deplete with heavy testing. Hits 429 if requests are too fast — pipeline enforces 5s delay between pages.

### Twikit (primary)
Pure Python, completely free, no API key needed. Authenticates via a real Twitter account. Cookie-based — logs in once, reuses session.

**Honest assessment:** Works well for research use. X occasionally changes internal endpoints causing temporary breakage (fix: `pip install twikit --upgrade`). Use a burner account to avoid suspension risk.

### Twscrape
No meaningful updates in ~11 months. Likely broken against current X endpoints. Not recommended.

### Official X API
Free tier is write-only — cannot search or read tweets. Basic plan starts at $200/month. Not viable for research use without budget approval.

---

## Error Handling

| Code | Meaning | Action |
|------|---------|--------|
| 200 | Success | Continue |
| 401 | Invalid API key | Stop |
| 402 | Payment required / credits exhausted | Trigger Twikit fallback |
| 403 | Access denied | Trigger Twikit fallback |
| 404 | Wrong endpoint | Stop |
| 429 | Rate limit exceeded | Retry with 10s wait, then Twikit fallback |
| 500 | Server error | Stop |

Retry logic: 3 attempts with 3s delay on Timeout / ConnectionError / RequestException.

---

## Logging

All modules use Python's `logging` module with three levels:

- `INFO` — normal pipeline progress
- `WARNING` — fallback triggers, duplicate removal, retries
- `ERROR` — failed requests, missing credentials, save failures

---

## Output Format

Each query produces files in three stages:

### Raw (`data/raw/query_timestamp.json`)
Complete API response, nothing stripped.

### Processed (`data/processed/query_timestamp.json`)

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
      "hashtags": ["Manipur", "flood"],
      "source": "twitterapi.io"
    }
  ]
}
```

### NLP Enriched (`data/nlp/query_timestamp.json`)

```json
{
  "metadata": {
    "query": "Manipur flood",
    "fetchedAt": "2026-06-17T07:45:52",
    "apiSource": "twitterapi.io",
    "tweetCount": 60,
    "preprocessedAt": "2026-06-20T20:58:00",
    "originalCount": 60,
    "afterFilter": 45,
    "afterDedup": 43,
    "finalCount": 43
  },
  "topics": [
    { "topic_id": 0, "words": ["flood", "relief", "manipur", "affected", "district"] }
  ],
  "events": [
    { "keyword": "flood", "count": 38, "spike_score": 0.21 }
  ],
  "tweets": [
    {
      "id": "...",
      "cleaned_text": "Manipur flood relief operations underway...",
      "hashtags": ["ManipurFlood", "Relief"],
      "mentions": ["NDRF", "CMO_Manipur"],
      "emojis": [],
      "urls": ["https://t.co/..."],
      "tokens": ["manipur", "flood", "relief", "operation", "underway"],
      "lemmatized_tokens": ["manipur", "flood", "relief", "operation", "underway"],
      "entities": [
        { "text": "Manipur", "label": "GPE" }
      ],
      "entity_freq": { "Manipur": 2 },
      "sentiment": {
        "vader": { "compound": -0.42, "label": "negative" },
        "roberta": { "label": "negative", "scores": { "negative": 0.71, "neutral": 0.22, "positive": 0.07 } },
        "final_label": "negative"
      },
      "keywords": ["flood", "relief", "manipur", "district", "operation"],
      "engagement": { "likes": 4, "retweets": 3, "replies": 0, "views": 500 }
    }
  ]
}
```

---

## NLP Preprocessing — 15 Enhancements

| # | Enhancement | Function | Output Field |
|---|-------------|----------|--------------|
| 1 | Hashtag extraction | `extract_hashtags()` | `hashtags` |
| 2 | Mention extraction | `extract_mentions()` | `mentions` |
| 3 | Emoji preservation | `extract_emojis()` | `emojis` |
| 4 | URL storage | `extract_urls()` | `urls` |
| 5 | Batch NLP processing | `nlp.pipe()` | — |
| 6 | spaCy tokenization + lemmatization | `token.lemma_` | `tokens` |
| 7 | Deterministic language detection | `DetectorFactory.seed=0` | — |
| 8 | Text deduplication + ID dedup | `deduplicate()` | — |
| 9 | Entity frequency | `Counter(entity_texts)` | `entity_freq` |
| 10 | Sentiment analysis (VADER + RoBERTa) | `get_sentiment()` | `sentiment` |
| 11 | Keyword extraction | `get_keywords()` | `keywords` |
| 12 | Event detection | `detect_events()` | `events` |
| 13 | Topic modelling (LDA) | `get_topics()` | `topics` |
| 14 | Lemmatized tokens | `token.lemma_` | `lemmatized_tokens` |
| 15 | Engagement metrics | `get_engagement()` | `engagement` |

---

## Dependencies

Key libraries:

```
requests
python-dotenv
twikit
nltk
spacy
langdetect
vaderSentiment
transformers
torch
gensim
```

Full list in `requirements.txt`.

---

## Repository

**Branch:** `twitter_acquisition`  
**Group:** Multimodal Broadcast Analytics, IIT Guwahati  
**Supervisor:** Prof. Prithwijit Guha  
**Alloted to:** Shlok Verman (M.Tech Scholar, IIT Guwahati)