"""
preprocess.py
Preprocessing pipeline for collected tweet data.
"""

import re
import json
import os
import logging
from collections import Counter
from datetime import datetime

from langdetect import detect, LangDetectException
from langdetect import DetectorFactory
DetectorFactory.seed = 0

import nltk
from nltk.corpus import stopwords
nltk.download("punkt",     quiet=True)
nltk.download("punkt_tab", quiet=True)
nltk.download("stopwords", quiet=True)

import spacy
import emoji as emoji_lib
from tqdm import tqdm

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

# P8: SKIP_DB_WRITE env flag — set to "1" on Colab to skip DB write
SKIP_DB_WRITE = os.environ.get("SKIP_DB_WRITE", "0") == "1"

if not SKIP_DB_WRITE:
    from db_manager import (get_conn, init_db, upsert_query, insert_fetch_run,
                            insert_tweets, insert_nlp, insert_entities,
                            insert_hashtags, insert_keywords,
                            insert_events)
    init_db()   # P1: init at module level — works whether called from main.py or directly

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

from sklearn.feature_extraction.text import TfidfVectorizer

log = logging.getLogger(__name__)

vader              = SentimentIntensityAnalyzer()
ROBERTA_MODEL      = "cardiffnlp/twitter-roberta-base-sentiment"
_roberta_tokenizer = AutoTokenizer.from_pretrained(ROBERTA_MODEL)
_roberta_model     = AutoModelForSequenceClassification.from_pretrained(ROBERTA_MODEL)
_roberta_model     = _roberta_model.to(DEVICE)
_roberta_model.eval()
ROBERTA_LABELS     = ["negative", "neutral", "positive"]

try:
    nlp = spacy.load("en_core_web_lg")
except OSError:
    log.warning(
        "en_core_web_lg not found — install it with "
        "`python -m spacy download en_core_web_lg`. Falling back to en_core_web_sm "
        "for this run (lower NER/entity quality)."
    )
    nlp = spacy.load("en_core_web_sm")
STOPWORDS = set(stopwords.words("english")) | {
    "rt", "amp", "via", "dm", "lol", "omg", "wtf", "smh",
    "imo", "imho", "irl", "fyi", "tbt", "icymi", "ootd",
    "tbh", "ngl", "idk", "rn", "ig",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def split_camel_case(token: str) -> list:
    """Split CamelCase/PascalCase into individual words. E.g. 'DelhiHeatwave' → ['Delhi', 'Heatwave']."""
    parts = re.sub(r"([a-z])([A-Z])", r"\1 \2", token).split()
    return parts if len(parts) > 1 else [token]

def extract_hashtags(text):
    """Return raw hashtag tokens (unsplit) — CamelCase splitting applied separately."""
    return re.findall(r"#(\w+)", text)

def expand_hashtags(hashtags: list) -> list:
    """Return a flat list of words by splitting CamelCase hashtags."""
    words = []
    for tag in hashtags:
        words.extend(split_camel_case(tag))
    return words

def extract_mentions(text): return re.findall(r"@(\w+)", text)
def extract_urls(text):     return re.findall(r"http\S+|www\S+", text)
def extract_emojis(text):   return [e["emoji"] for e in emoji_lib.emoji_list(text)]

def clean_text(text: str) -> str:
    if not text: return ""
    text = re.sub(r"http\S+|www\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#(\w+)", r"\1", text)
    text = re.sub(r"\n+", " ", text)
    text = emoji_lib.replace_emoji(text, replace="")   # Fix 5: strip emojis
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# Stage 2 — Filtering
# ─────────────────────────────────────────────────────────────────────────────

def is_valid(tweet: dict, allowed_langs=["en"]) -> bool:
    if tweet.get("isRetweet"): return False
    cleaned = clean_text(tweet.get("text", ""))
    if len(cleaned.split()) < 5: return False
    tweet_lang = tweet.get("lang", "")
    if tweet_lang and tweet_lang not in allowed_langs: return False
    if not tweet_lang:
        # Fix 7: skip langdetect for very short tweets — unreliable below 4 words
        if len(cleaned.split()) < 4:
            return False
        try:
            if detect(cleaned) not in allowed_langs: return False
        except LangDetectException: return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Stage 3 — Deduplication
# ─────────────────────────────────────────────────────────────────────────────

def deduplicate(tweets: list) -> list:
    seen_ids, seen_texts, unique = set(), set(), []
    for tweet in tweets:
        tid  = tweet.get("id")
        text = clean_text(tweet.get("text", "")).lower().strip()
        if tid and tid in seen_ids: continue
        if text and text in seen_texts: continue
        if tid:   seen_ids.add(tid)
        if text:  seen_texts.add(text)
        unique.append(tweet)
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# NLP helpers
# ─────────────────────────────────────────────────────────────────────────────

def batch_roberta_sentiment(texts: list) -> list:
    results, batch_size = [], 16
    for i in tqdm(range(0, len(texts), batch_size), desc="  RoBERTa sentiment", leave=False):
        batch = texts[i: i + batch_size]
        try:
            encoded = _roberta_tokenizer(batch, return_tensors="pt", truncation=True, max_length=512, padding=True)
            inputs  = {k: v.to(DEVICE) for k, v in encoded.items()}
            with torch.no_grad():
                logits = _roberta_model(**inputs).logits
            for probs in torch.softmax(logits, dim=1).cpu().tolist():
                label  = ROBERTA_LABELS[probs.index(max(probs))]
                scores = {l: round(p, 4) for l, p in zip(ROBERTA_LABELS, probs)}
                results.append({"label": label, "scores": scores})
        except Exception:
            for _ in batch:
                results.append({"label": "neutral", "scores": {"negative": 0.0, "neutral": 1.0, "positive": 0.0}})
    return results


def get_vader_sentiment(text: str) -> dict:
    s = vader.polarity_scores(text)
    c = s["compound"]
    return {"compound": round(c,4), "pos": round(s["pos"],4), "neu": round(s["neu"],4),
            "neg": round(s["neg"],4), "label": "positive" if c>=0.05 else "negative" if c<=-0.05 else "neutral"}


def get_final_sentiment(vader_result: dict, roberta_result: dict) -> dict:
    """
    Confidence-based sentiment ensemble (Fix 1).

    Previously final_label was always roberta['label'], ignoring VADER
    entirely except for storage. Instead: each model reports a confidence
    score — RoBERTa's is its max softmax probability, VADER's is the
    absolute value of its compound score (already 0-1). Whichever model
    is more confident about its own call wins. Ties favour RoBERTa, since
    it's generally the stronger model for short, informal tweet text.
    """
    roberta_scores = roberta_result.get("scores", {}) or {}
    roberta_conf   = max(roberta_scores.values()) if roberta_scores else 0.0
    vader_conf     = abs(vader_result.get("compound", 0.0))

    if roberta_conf >= vader_conf:
        return {"label": roberta_result.get("label", "neutral"),
                "confidence": round(roberta_conf, 4), "source": "roberta"}
    else:
        return {"label": vader_result.get("label", "neutral"),
                "confidence": round(vader_conf, 4), "source": "vader"}


def batch_tfidf_keywords(texts: list, top_n=10) -> list:
    if len(texts) < 2: return [[] for _ in texts]
    try:
        vec    = TfidfVectorizer(max_features=500, stop_words="english", ngram_range=(1,2),
                                min_df=2, sublinear_tf=True)
        matrix = vec.fit_transform(texts)
        terms  = vec.get_feature_names_out()
        return [[t for t,s in sorted(zip(terms, row.toarray()[0]), key=lambda x:x[1], reverse=True)[:top_n] if s>0]
                for row in matrix]
    except Exception:
        return [[] for _ in texts]


def detect_events(tweets: list, top_n=5) -> list:
    all_kw = []
    for t in tweets: all_kw.extend(t.get("keywords", []))
    freq  = Counter(all_kw)
    total = sum(freq.values()) or 1
    return [{"keyword": kw, "count": cnt, "freq_ratio": round(cnt/total, 4)}
            for kw, cnt in freq.most_common(top_n)]


def get_engagement(tweet: dict) -> dict:
    return {
        "likes":     tweet.get("likeCount",    tweet.get("favorite_count", 0)),
        "retweets":  tweet.get("retweetCount", tweet.get("retweet_count",  0)),
        "replies":   tweet.get("replyCount",   tweet.get("reply_count",    0)),
        "views":     tweet.get("viewCount",    tweet.get("view_count",     None)),
        "bookmarks": tweet.get("bookmarkCount", None),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def preprocess_file(filepath: str, output_dir: str = "data/nlp"):
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    original_count = len(data.get("tweets", []))
    tweets = data.get("tweets", [])

    tweets       = [t for t in tweets if is_valid(t)]
    after_filter = len(tweets)
    tweets       = deduplicate(tweets)
    after_dedup  = len(tweets)

    # P4: handle None return
    if not tweets:
        log.warning(f"  {original_count} → 0 tweets after filtering — skipping {filepath}")
        return None

    for tweet in tweets:
        raw = tweet.get("text", "")
        tweet["hashtags"]     = extract_hashtags(raw)
        tweet["mentions"]     = extract_mentions(raw)
        tweet["emojis"]       = extract_emojis(raw)
        tweet["urls"]         = extract_urls(raw)
        tweet["cleaned_text"] = clean_text(raw)

    cleaned_texts = [t["cleaned_text"] for t in tweets]
    docs = list(tqdm(nlp.pipe(cleaned_texts, batch_size=50), total=len(cleaned_texts), desc="  spaCy NER", leave=False))

    for tweet, doc in zip(tweets, docs):
        tweet["tokens"]            = [t.text.lower() for t in doc if t.is_alpha and t.text.lower() not in STOPWORDS]
        tweet["lemmatized_tokens"] = [t.lemma_.lower() for t in doc if t.is_alpha and t.lemma_.lower() not in STOPWORDS]
        # Fix 3: inject CamelCase-split hashtag words
        ht_words = [w.lower() for w in expand_hashtags(tweet.get("hashtags", [])) if w.lower() not in STOPWORDS]
        tweet["tokens"]            += ht_words
        tweet["lemmatized_tokens"] += ht_words
        # Fix 4: normalize entity case — title-case so "india" and "India" merge
        entities                   = [{"text": e.text.title(), "label": e.label_} for e in doc.ents]
        tweet["entities"]          = entities
        tweet["entity_freq"]       = dict(Counter([e["text"] for e in entities]))
        tweet["engagement"]        = get_engagement(tweet)
        raw_date = tweet.get("createdAt", "")
        try:
            tweet["createdAt"] = datetime.strptime(raw_date, "%a %b %d %H:%M:%S %z %Y").isoformat()
        except (ValueError, TypeError):
            pass

    for tweet in tqdm(tweets, desc="  VADER sentiment", leave=False):
        tweet["sentiment"] = {"vader": get_vader_sentiment(tweet["cleaned_text"])}

    roberta_results = batch_roberta_sentiment(cleaned_texts)
    for tweet, roberta in zip(tweets, roberta_results):
        tweet["sentiment"]["roberta"] = roberta
        final = get_final_sentiment(tweet["sentiment"]["vader"], roberta)
        tweet["sentiment"]["final_label"]      = final["label"]
        tweet["sentiment"]["final_confidence"] = final["confidence"]
        tweet["sentiment"]["final_source"]     = final["source"]

    tfidf_keywords = batch_tfidf_keywords(cleaned_texts)
    for tweet, kws in zip(tweets, tfidf_keywords):
        tweet["keywords"] = kws

    # Topic modelling no longer runs here — BERTopic now runs PER QUERY
    # (pooling tweets across all fetch_runs) in ingest.py, after ingestion.
    topics = []
    events = detect_events(tweets)

    result = {
        "metadata": {
            **data.get("metadata", {}),
            "preprocessedAt": datetime.now().isoformat(),
            "originalCount":  original_count,
            "afterFilter":    after_filter,
            "afterDedup":     after_dedup,
            "finalCount":     len(tweets),
            "device":         str(DEVICE),
        },
        "topics": topics,
        "events": events,
        "tweets": tweets,
    }

    os.makedirs(output_dir, exist_ok=True)
    filename = os.path.basename(filepath)
    out_path = os.path.join(output_dir, filename)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    log.info(f"  ✓ {original_count} → {len(tweets)} tweets | Saved → {out_path}")

    # P1+P2+P3: DB auto-write — inside preprocess_file(), correct indentation
    # P8: skip if SKIP_DB_WRITE=1 (Colab)
    if not SKIP_DB_WRITE:
        # P3: check if this nlp_file already ingested
        nlp_fname = os.path.basename(out_path)
        with get_conn() as conn:
            existing = conn.execute(
                "SELECT id FROM fetch_runs WHERE nlp_file = ?", (nlp_fname,)
            ).fetchone()
            if existing:
                log.warning(f"  Already ingested {nlp_fname} — skipping DB write")
            else:
                query_id = upsert_query(conn, result["metadata"].get("query", "unknown"))
                run_id   = insert_fetch_run(conn, query_id, result["metadata"],
                                            processed_file=os.path.basename(filepath),
                                            nlp_file=nlp_fname)
                insert_tweets(conn, run_id, data.get("tweets", []),
                              default_source=result["metadata"].get("apiSource"))
                insert_hashtags(conn, run_id, data.get("tweets", []))
                insert_nlp(conn, run_id, tweets)
                insert_entities(conn, run_id, tweets)
                insert_keywords(conn, run_id, tweets)
                insert_events(conn, run_id, events)
                log.info(f"  ✓ Written to pipeline.db")

    return out_path


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    processed_dir = "data/processed"
    files = []
    for root, dirs, filenames in os.walk(processed_dir):
        for f in filenames:
            if f.endswith(".json"):
                files.append(os.path.join(root, f))

    log.info(f"Found {len(files)} processed files")
    for fp in tqdm(files, desc="Files"):
        log.info(f"Processing: {fp}")
        result = preprocess_file(fp)
        # P4: handle None return in __main__
        if result is None:
            log.warning(f"  Skipped (no tweets after filtering): {fp}")