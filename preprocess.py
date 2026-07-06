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
                            insert_topics, insert_events)
    init_db()   # P1: init at module level — works whether called from main.py or directly

DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

from sklearn.feature_extraction.text import TfidfVectorizer

log = logging.getLogger(__name__)

try:
    from bertopic import BERTopic
    BERTOPIC_AVAILABLE = True
except ImportError:
    BERTOPIC_AVAILABLE = False
    log.warning("BERTopic not installed — topic modelling disabled.")

vader              = SentimentIntensityAnalyzer()
ROBERTA_MODEL      = "cardiffnlp/twitter-roberta-base-sentiment"
_roberta_tokenizer = AutoTokenizer.from_pretrained(ROBERTA_MODEL)
_roberta_model     = AutoModelForSequenceClassification.from_pretrained(ROBERTA_MODEL)
_roberta_model     = _roberta_model.to(DEVICE)
_roberta_model.eval()
ROBERTA_LABELS     = ["negative", "neutral", "positive"]

nlp       = spacy.load("en_core_web_sm")
STOPWORDS = set(stopwords.words("english"))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def extract_hashtags(text): return re.findall(r"#(\w+)", text)
def extract_mentions(text): return re.findall(r"@(\w+)", text)
def extract_urls(text):     return re.findall(r"http\S+|www\S+", text)
def extract_emojis(text):   return [e["emoji"] for e in emoji_lib.emoji_list(text)]

def clean_text(text: str) -> str:
    if not text: return ""
    text = re.sub(r"http\S+|www\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#(\w+)", r"\1", text)
    text = re.sub(r"\n+", " ", text)
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


def batch_tfidf_keywords(texts: list, top_n=10) -> list:
    if len(texts) < 2: return [[] for _ in texts]
    try:
        vec    = TfidfVectorizer(max_features=500, stop_words="english", ngram_range=(1,2))
        matrix = vec.fit_transform(texts)
        terms  = vec.get_feature_names_out()
        return [[t for t,s in sorted(zip(terms, row.toarray()[0]), key=lambda x:x[1], reverse=True)[:top_n] if s>0]
                for row in matrix]
    except Exception:
        return [[] for _ in texts]


def get_topics_bertopic(texts: list) -> list:
    """P9: BERTopic with small-dataset UMAP/HDBSCAN config — fixes topics=0."""
    if not BERTOPIC_AVAILABLE or len(texts) < 5:
        return []
    try:
        from umap import UMAP
        from hdbscan import HDBSCAN

        n = len(texts)
        umap_model = UMAP(
            n_neighbors  = min(n - 1, 15),
            n_components = min(n - 1, 5),
            min_dist     = 0.0,
            metric       = "cosine",
            random_state = 42
        )
        hdbscan_model = HDBSCAN(
            min_cluster_size = 2,
            min_samples      = 1,
            prediction_data  = True
        )
        model = BERTopic(
            umap_model     = umap_model,
            hdbscan_model  = hdbscan_model,
            verbose        = False,
            nr_topics      = "auto",
            min_topic_size = 2
        )
        topics, _ = model.fit_transform(texts)
        info      = model.get_topic_info()
        result    = []
        for _, row in info[info["Topic"] != -1].head(5).iterrows():
            words = [w for w, _ in model.get_topic(row["Topic"])]
            result.append({"topic_id": int(row["Topic"]), "words": words[:5]})
        return result
    except Exception as e:
        log.warning(f"BERTopic failed: {e}")  # now shows real error
        return []


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
        entities                   = [{"text": e.text, "label": e.label_} for e in doc.ents]
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
        tweet["sentiment"]["roberta"]     = roberta
        tweet["sentiment"]["final_label"] = roberta["label"]

    tfidf_keywords = batch_tfidf_keywords(cleaned_texts)
    for tweet, kws in zip(tweets, tfidf_keywords):
        tweet["keywords"] = kws

    topics = get_topics_bertopic(cleaned_texts)
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
                insert_topics(conn, run_id, topics)
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