"""
preprocess.py
Preprocessing pipeline for collected tweet data.
Stages:
    1. Text cleaning
    2. Filtering (retweets, language, empty)
    3. Deduplication
    4. NLP enrichment (tokens, stopwords, NER)
"""

import re
import json
import os
from datetime import datetime
from langdetect import detect, LangDetectException
import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
import spacy

# ── One-time NLTK downloads ───────────────────────────────────────────────────
nltk.download("punkt", quiet=True)
nltk.download("punkt_tab", quiet=True)
nltk.download("stopwords", quiet=True)

# ── Load spaCy model ──────────────────────────────────────────────────────────
nlp = spacy.load("en_core_web_sm")
STOPWORDS = set(stopwords.words("english"))


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — Text Cleaning
# ─────────────────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Remove URLs, mentions, extra whitespace, normalize newlines."""
    if not text:
        return ""
    text = re.sub(r"http\S+|www\S+", "", text)          # remove URLs
    text = re.sub(r"@\w+", "", text)                     # remove @mentions
    text = re.sub(r"\n+", " ", text)                     # flatten newlines
    text = re.sub(r"\s+", " ", text)                     # collapse spaces
    text = text.strip()
    return text


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — Filtering
# ─────────────────────────────────────────────────────────────────────────────

def is_valid(tweet: dict, allowed_langs: list = ["en"]) -> bool:
    """Return False if tweet should be dropped."""

    # Drop retweets
    if tweet.get("isRetweet"):
        return False

    text = tweet.get("text", "")

    # Drop empty or very short text
    cleaned = clean_text(text)
    if len(cleaned.split()) < 5:
        return False

    # Drop non-target languages
    tweet_lang = tweet.get("lang", "")
    if tweet_lang and tweet_lang not in allowed_langs:
        return False

    # Verify with langdetect as backup
    if not tweet_lang:
        try:
            detected = detect(cleaned)
            if detected not in allowed_langs:
                return False
        except LangDetectException:
            return False

    return True


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3 — Deduplication
# ─────────────────────────────────────────────────────────────────────────────

def deduplicate(tweets: list) -> list:
    """Remove duplicate tweets by id."""
    seen = set()
    unique = []
    for tweet in tweets:
        tid = tweet.get("id")
        if tid and tid not in seen:
            seen.add(tid)
            unique.append(tweet)
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 4 — NLP Enrichment
# ─────────────────────────────────────────────────────────────────────────────

def enrich(tweet: dict) -> dict:
    """Add tokens, filtered tokens, and named entities to tweet."""
    text = clean_text(tweet.get("text", ""))

    # Tokenize and remove stopwords/punctuation
    tokens = word_tokenize(text.lower())
    filtered_tokens = [
        t for t in tokens
        if t.isalpha() and t not in STOPWORDS
    ]

    # Named Entity Recognition via spaCy
    doc = nlp(text)
    entities = [
        {"text": ent.text, "label": ent.label_}
        for ent in doc.ents
    ]

    tweet["cleaned_text"]    = text
    tweet["tokens"]          = filtered_tokens
    tweet["entities"]        = entities

    # Normalize datetime
    raw_date = tweet.get("createdAt", "")
    try:
        dt = datetime.strptime(raw_date, "%a %b %d %H:%M:%S %z %Y")
        tweet["createdAt"] = dt.isoformat()
    except (ValueError, TypeError):
        pass

    return tweet


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — Run full preprocessing on a processed JSON file
# ─────────────────────────────────────────────────────────────────────────────

def preprocess_file(filepath: str, output_dir: str = "data/nlp") -> str:
    """
    Load a processed JSON, run all preprocessing stages,
    save to data/nlp/ and return output filepath.
    """
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    original_count = len(data.get("tweets", []))
    tweets = data.get("tweets", [])

    # Stage 1+2 — Clean and filter
    tweets = [t for t in tweets if is_valid(t)]
    after_filter = len(tweets)

    # Stage 3 — Deduplicate
    tweets = deduplicate(tweets)
    after_dedup = len(tweets)

    # Stage 4 — NLP enrichment
    tweets = [enrich(t) for t in tweets]

    # Build output
    result = {
        "metadata": {
            **data.get("metadata", {}),
            "preprocessedAt": datetime.now().isoformat(),
            "originalCount":  original_count,
            "afterFilter":    after_filter,
            "afterDedup":     after_dedup,
            "finalCount":     len(tweets),
        },
        "tweets": tweets
    }

    # Save
    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.basename(filepath)
    out_path = os.path.join(output_dir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"  ✓ {original_count} → {len(tweets)} tweets after preprocessing")
    print(f"  ✓ Saved → {out_path}")
    return out_path


if __name__ == "__main__":
    # Run on all files in data/processed/
    processed_dir = "data/processed"
    files = [
        os.path.join(processed_dir, f)
        for f in os.listdir(processed_dir)
        if f.endswith(".json")
    ]

    print(f"Found {len(files)} processed files\n")
    for fp in files:
        print(f"Processing: {fp}")
        preprocess_file(fp)
        print()