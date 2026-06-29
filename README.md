# Social Media Acquisition Pipeline

Twitter data collection and NLP preprocessing pipeline for the Multimodal Broadcast Analytics System, IIT Guwahati.

Built as part of a research internship under Prof. Prithwijit Guha, this pipeline supports multi-source news summarization research by collecting, cleaning, and enriching Twitter data at scale.

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
├── paginator.py           # multi-page tweet collection with cursor-based deduplication
├── filenamegen.py         # timestamped slug-based filename generation
├── preprocess.py          # NLP preprocessing pipeline (cleaning → filtering → enrichment)
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

### Local

```bash
# activate venv
venv\Scripts\activate

# install dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# add queries to queries.txt, then run acquisition
python main.py

# run NLP preprocessing on collected data
python preprocess.py

# export to CSV for review
python export_csv.py
```

### Google Colab (recommended for preprocessing — GPU available)

```python
# Cell 1 — Clone repo
!git clone -b twitter_acquisition https://github.com/Wik-Hrit/social-media-pipeline-test.git
%cd social-media-pipeline-test

# Cell 2 — Install dependencies
!pip install -r requirements.txt
!python -m spacy download en_core_web_sm

# Cell 3 — NLTK downloads
import nltk
nltk.download('punkt')
nltk.download('punkt_tab')
nltk.download('stopwords')

# Cell 4 — Run preprocessing (T4 GPU auto-detected)
!python preprocess.py
```

> Set runtime to **T4 GPU** (Runtime → Change runtime type) before running for faster RoBERTa inference.

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
main.py  (orchestrator — deduplicates queries, logging, timing)
    ↓
paginator.py  (cursor-based multi-page collection, seen_ids dedup)
    ↓
fetch_tweets.py
    ├── Primary:  twikit_client.py  (cookie-based, free, no API key)
    └── Fallback: twitter_client.py → twitterapi.io  (429/402/403 triggers fallback)
    ↓
error_handler.py  (status code handling, retry logic)
    ↓
save_raw.py       →  data/raw/        (full API response)
save_processed.py →  data/processed/  (clean fields + metadata + source tracking)
    ↓
preprocess.py     →  data/nlp/        (NLP enrichment — sentiment, NER, topics, keywords)
    ↓
export_csv.py     →  data/csv/        (one CSV per query topic)
```

---

## Fallback Logic

The pipeline uses a two-source strategy with automatic failover:

- **Primary:** Twikit (cookie-based, completely free, no API key needed)
- **Fallback:** twitterapi.io (activates automatically on 429 / 402 / 403 errors)

Source is tracked **per tweet** (`source` field) and at file level (`apiSource` in metadata).

To set up Twikit, add to `.env`:

```
TWITTER_USERNAME=your_twitter_handle
TWITTER_EMAIL=your@email.com
TWITTER_PASSWORD=yourpassword
TWIKIT_COOKIES_FILE=twikit_cookies.json
```

First run logs in and saves `twikit_cookies.json`. Subsequent runs reuse cookies silently. If cookies expire, the file is auto-deleted and re-login happens on the next run.

> Use a dedicated/burner Twitter account — not your personal account.

---

## API Options Evaluated

### twitterapi.io (current fallback)
Unofficial wrapper around X's internal API. 100K free credits on signup, then $0.15/1000 tweets. No account login needed. Reliable for research-scale collection.

**Limitations:** Free credits deplete with heavy testing. Hits 429 if requests are too fast — pipeline enforces 5s delay between pages.

### Twikit (primary)
Pure Python, completely free, no API key needed. Authenticates via a real Twitter account. Cookie-based — logs in once, reuses session. Tested and integrated.

**Current status:** Temporarily broken due to a library-level auth issue (`KEY_BYTE indices`) caused by Twitter's internal API changes. Pipeline auto-falls back to twitterapi.io. Will auto-activate as primary once the library is patched (`pip install twikit --upgrade`).

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

Each query produces files across three stages:

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
    "finalCount": 43,
    "device": "cpu"
  },
  "topics": [
    { "topic_id": 0, "words": ["flood", "relief", "manipur", "affected", "district"] }
  ],
  "events": [
    { "keyword": "flood", "count": 38, "freq_ratio": 0.21 }
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
      "lemmatized_tokens": ["manipur", "flood", "relieve", "operation", "underway"],
      "entities": [{ "text": "Manipur", "label": "GPE" }],
      "entity_freq": { "Manipur": 2 },
      "sentiment": {
        "vader": { "compound": -0.42, "label": "negative" },
        "roberta": {
          "label": "negative",
          "scores": { "negative": 0.71, "neutral": 0.22, "positive": 0.07 }
        },
        "final_label": "negative"
      },
      "keywords": ["flood", "relief", "manipur", "district", "operation"],
      "engagement": { "likes": 4, "retweets": 3, "replies": 0, "views": 500 },
      "source": "twitterapi.io"
    }
  ]
}
```

---

## NLP Preprocessing — Enhancements

| # | Enhancement | Approach | Output Field |
|---|-------------|----------|--------------|
| 1 | Hashtag extraction | Regex `#(\w+)` | `hashtags` |
| 2 | Mention extraction | Regex `@(\w+)` | `mentions` |
| 3 | Emoji preservation | `emoji` library (all Unicode blocks) | `emojis` |
| 4 | URL storage | Regex, stored before cleaning | `urls` |
| 5 | Batch NLP | `nlp.pipe()` — batch_size=50 | — |
| 6 | Tokenization | spaCy surface forms, lowercased | `tokens` |
| 7 | Lemmatization | spaCy `token.lemma_` | `lemmatized_tokens` |
| 8 | Deterministic lang detection | `DetectorFactory.seed=0` | — |
| 9 | Deduplication | ID dedup + text dedup | — |
| 10 | Entity frequency | `Counter` over NER entities | `entity_freq` |
| 11 | Sentiment — rule-based | VADER | `sentiment.vader` |
| 12 | Sentiment — transformer | RoBERTa (twitter-trained, batched, GPU-aware) | `sentiment.roberta` |
| 13 | Keyword extraction | TF-IDF across batch (scikit-learn) | `keywords` |
| 14 | Event detection | Keyword freq_ratio across tweets | `events` (file-level) |
| 15 | Topic modelling | BERTopic (replaces LDA, min 5 tweets) | `topics` (file-level) |
| 16 | Engagement metrics | likes, retweets, replies, views | `engagement` |

> **Note:** BERTopic requires minimum 5 tweets per file to run. Files with fewer tweets skip topic modelling gracefully.

---

## Testing

| Environment | Status | Notes |
|-------------|--------|-------|
| Local (Windows, CPU) | ✅ Tested | 106 files, all processed |
| Google Colab (T4 GPU) | ✅ Tested | RoBERTa batching ~10x faster on GPU |

---

## Dependencies

```
requests
python-dotenv
twikit
nltk
spacy
langdetect
emoji
vaderSentiment
transformers
torch
bertopic
scikit-learn
tqdm
gensim
```

Full pinned versions in `requirements.txt`.

---

## Repository

**Branch:** `twitter_acquisition`
**Group:** Multimodal Broadcast Analytics, IIT Guwahati
**Supervisor:** Prof. Prithwijit Guha
**Assigned to:** Shlok Verman (M.Tech Scholar, IIT Guwahati)