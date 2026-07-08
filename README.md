# Social Media NLP Pipeline
**Multimodal Broadcast Analytics System — IIT Guwahati**

A complete end-to-end pipeline for acquiring, preprocessing, and analysing Twitter/X data across multiple query topics using NLP techniques including sentiment analysis (VADER + RoBERTa), named entity recognition (spaCy), topic modelling (BERTopic), and keyword extraction (TF-IDF).

---

## Pipeline Overview

```
queries.txt
    │
    ▼
fetch_tweets.py / paginator.py      ← Twikit (primary) + twitterapi.io (fallback)
    │
    ▼
save_raw.py → data/raw/             ← Raw API response
    │
    ▼
save_processed.py → data/processed/ ← Cleaned tweet fields
    │
    ▼
preprocess.py → data/nlp/           ← NLP enrichment (spaCy, VADER, RoBERTa, BERTopic, TF-IDF)
    │
    ▼
ingest.py → pipeline.db             ← SQLite (9 tables)
    │
    ▼
analysis.py → data/analysis/        ← JSON results
    │
    ▼
visualise.py → data/charts/         ← 7 charts (PNG)
sentiment_report.py → report.md     ← Auto-generated insight report
pipeline_stats.py                   ← Health dashboard
```

---

## Setup

### 1. Clone the repo
```bash
git clone https://github.com/Wik-Hrit/social-media-pipeline-test.git
cd social-media-pipeline-test
git checkout twitter_acquisition
```

### 2. Create virtual environment
```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux/Mac
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
python -m spacy download en_core_web_sm
```

### 4. Configure environment
Create a `.env` file in the root directory:
```
TWITTER_API_KEY=your_twitterapi_io_key
TWITTER_USERNAME=your_twitter_username
TWITTER_EMAIL=your_twitter_email
TWITTER_PASSWORD=your_twitter_password
```

### 5. Add queries
Edit `queries.txt` — one query per line:
```
Delhi Heatwave
OpenAI
NEET 2026
IPL 2026
```

---

## Running the Pipeline

### Full acquisition run
```bash
python main.py
```
Fetches tweets for all queries in `queries.txt`. Runs on a scheduler (`RUN_INTERVAL_HOURS` in `config.py`).

### Preprocess NLP
```bash
python preprocess.py
```
Runs spaCy NER, VADER sentiment, RoBERTa sentiment, BERTopic, TF-IDF on all processed files.

### Ingest to database
```bash
python ingest.py
```
Migrates all `data/processed/` and `data/nlp/` JSON files into `pipeline.db`.

### Verify database
```bash
python verify_db.py
```
Prints row counts for all 9 tables + entity label distribution.

### Run analysis
```bash
python analysis.py
```
Generates `data/analysis/analysis_results.json` with sentiment, entities, hashtags, keywords, engagement, and volume data.

### Generate charts
```bash
python visualise.py
```
Saves 7 charts to `data/charts/`.

### Health dashboard
```bash
python pipeline_stats.py
```
One-command overview of the entire pipeline state.

### Auto insight report
```bash
python sentiment_report.py
```
Generates `data/analysis/report.md` with human-readable findings.

### Export to CSV
```bash
python export_csv.py
```
Exports NLP data grouped by topic to `data/csv/`.

---

## Database Schema (9 Tables)

| Table | Description |
|-------|-------------|
| `queries` | Unique query strings (24) |
| `fetch_runs` | One row per processed JSON file (148) |
| `tweets` | Base tweet fields — text, author, engagement (1,423) |
| `tweet_nlp` | NLP enrichment — sentiment, tokens, entities (1,121) |
| `entities` | Named entities with NER label and frequency (12,320) |
| `hashtags` | One row per hashtag per tweet (5,587) |
| `keywords` | TF-IDF keywords per tweet (18,686) |
| `topics` | BERTopic output per fetch run (290) |
| `events` | Keyword frequency events (515) |

---

## NLP Stack

| Task | Library | Model |
|------|---------|-------|
| Text cleaning | spaCy | `en_core_web_sm` |
| Named Entity Recognition | spaCy | `en_core_web_sm` |
| Sentiment (lexical) | VADER | `vaderSentiment` |
| Sentiment (transformer) | HuggingFace | `cardiffnlp/twitter-roberta-base-sentiment` |
| Topic modelling | BERTopic | UMAP + HDBSCAN |
| Keyword extraction | scikit-learn | TF-IDF |

**Final sentiment label** is determined by RoBERTa when confidence > 0.6, else VADER.

---

## Output Files

```
data/
├── raw/           ← Raw API responses (JSON)
├── processed/     ← Cleaned tweet data (JSON)
├── nlp/           ← NLP-enriched data (JSON)
├── analysis/
│   ├── analysis_results.json
│   └── report.md
├── charts/
│   ├── 01_sentiment_distribution.png
│   ├── 02_wordcloud_keywords.png
│   ├── 03_top_hashtags.png
│   ├── 04_engagement_comparison.png
│   ├── 05_source_distribution.png
│   ├── 06_vader_roberta_agreement.png
│   └── 07_tweet_volume_over_time.png
└── csv/           ← Per-topic CSV exports
```

---

## Configuration (`config.py`)

| Setting | Default | Description |
|---------|---------|-------------|
| `QUERY_TYPE` | `"Latest"` | Latest or Top tweets |
| `COUNT` | `20` | Tweets per page |
| `MAX_PAGES` | `3` | Pagination pages (twitterapi.io only) |
| `RUN_INTERVAL_HOURS` | `2` | Scheduler interval |
| `MIN_CREDITS_THRESHOLD` | `500` | Credit warning threshold |

---

## Project Structure

```
├── main.py              # Pipeline entry point + scheduler
├── config.py            # Central configuration
├── fetch_tweets.py      # Single-page fetch (Twikit + fallback)
├── paginator.py         # Cursor-based pagination (twitterapi.io)
├── twikit_client.py     # Cookie-based Twitter client
├── twitter_client.py    # twitterapi.io HTTP client
├── save_raw.py          # Save raw API response
├── save_processed.py    # Save cleaned tweet fields
├── preprocess.py        # Full NLP pipeline
├── ingest.py            # DB migration from JSON files
├── db_manager.py        # SQLite schema + insert functions
├── analysis.py          # Compute analysis from DB → JSON
├── visualise.py         # Generate charts from JSON
├── pipeline_stats.py    # Health dashboard
├── sentiment_report.py  # Auto insight report (Markdown)
├── export_csv.py        # Export to CSV by topic
├── verify_db.py         # DB sanity check
├── error_handler.py     # HTTP response handler
├── filenamegen.py       # Timestamped filename generator
└── queries.txt          # Query topics (one per line)
```

---

## Author
**Hritwik Varma** — B.Tech ECE, BIT Mesra  
Research Intern, IIT Guwahati (May–July 2026)  
Supervisor: Prof. Prithwijit Guha | Alloted to: Shlok Verman (M.Tech Scholar)  
GitHub: [github.com/Wik-Hrit](https://github.com/Wik-Hrit)