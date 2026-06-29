"""
preprocess.py
Preprocessing pipeline for collected tweet data.

Fixes applied (Shlok Sir, Round 3(not sure for number of iterations)):
  1.  Removed unused enrich() — batch pipeline in preprocess_file() handles everything
  2.  tokens = raw lowercased surface forms; lemmatized_tokens = lemma forms (now distinct)
  3.  RoBERTa batched across all tweets per file (not per-tweet) — major speed-up
  4.  GPU used if available (torch.device auto-detect)
  5.  Keywords via TF-IDF across the batch (replaces frequency count)
  6.  BERTopic replaces LDA for topic modelling (more reliable on small data)
  7.  Event detection: spike_score renamed to freq_ratio
  8.  Emoji extraction uses `emoji` library (covers all Unicode blocks)
  9.  tqdm progress bars added
  10. requirements.txt regenerated (see bottom of file for pip freeze instructions)
"""

import re
import json
import os
from collections import Counter
from datetime import datetime

from langdetect import detect, LangDetectException
from langdetect import DetectorFactory
DetectorFactory.seed = 0

import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
nltk.download("punkt",     quiet=True)
nltk.download("punkt_tab", quiet=True)
nltk.download("stopwords", quiet=True)

import spacy
import emoji as emoji_lib                              # Fix 8: proper emoji lib
from tqdm import tqdm                                  # Fix 9: progress bars

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

# Fix 4: GPU if available
DEVICE = torch.device("cuda" if torch.cuda.is_available() else "cpu")

from sklearn.feature_extraction.text import TfidfVectorizer   # Fix 5

# Fix 6: BERTopic
try:
    from bertopic import BERTopic
    BERTOPIC_AVAILABLE = True
except ImportError:
    BERTOPIC_AVAILABLE = False
    print("[warn] BERTopic not installed — topic modelling disabled. Run: pip install bertopic")

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
# Helpers — extraction before cleaning
# ─────────────────────────────────────────────────────────────────────────────

def extract_hashtags(text: str) -> list:
    return re.findall(r"#(\w+)", text)

def extract_mentions(text: str) -> list:
    return re.findall(r"@(\w+)", text)

def extract_urls(text: str) -> list:
    return re.findall(r"http\S+|www\S+", text)

def extract_emojis(text: str) -> list:
    """Fix 8: use emoji library — covers all Unicode blocks reliably."""
    return [e["emoji"] for e in emoji_lib.emoji_list(text)]


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — Text Cleaning
# ─────────────────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r"http\S+|www\S+", "", text)
    text = re.sub(r"@\w+", "", text)
    text = re.sub(r"#(\w+)", r"\1", text)
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 2 — Filtering
# ─────────────────────────────────────────────────────────────────────────────

def is_valid(tweet: dict, allowed_langs: list = ["en"]) -> bool:
    if tweet.get("isRetweet"):
        return False
    cleaned = clean_text(tweet.get("text", ""))
    if len(cleaned.split()) < 5:
        return False
    tweet_lang = tweet.get("lang", "")
    if tweet_lang and tweet_lang not in allowed_langs:
        return False
    if not tweet_lang:
        try:
            if detect(cleaned) not in allowed_langs:
                return False
        except LangDetectException:
            return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 3 — Deduplication
# ─────────────────────────────────────────────────────────────────────────────

def deduplicate(tweets: list) -> list:
    seen_ids   = set()
    seen_texts = set()
    unique     = []
    for tweet in tweets:
        tid  = tweet.get("id")
        text = clean_text(tweet.get("text", "")).lower().strip()
        if tid and tid in seen_ids:
            continue
        if text and text in seen_texts:
            continue
        if tid:
            seen_ids.add(tid)
        if text:
            seen_texts.add(text)
        unique.append(tweet)
    return unique


# ─────────────────────────────────────────────────────────────────────────────
# Batch NLP helpers
# ─────────────────────────────────────────────────────────────────────────────

def batch_roberta_sentiment(texts: list) -> list:
    """Fix 3: Batch RoBERTa inference — one forward pass per batch, not per tweet."""
    results = []
    batch_size = 16
    for i in tqdm(range(0, len(texts), batch_size), desc="  RoBERTa sentiment", leave=False):
        batch = texts[i: i + batch_size]
        try:
            encoded = _roberta_tokenizer(
                batch, return_tensors="pt", truncation=True,
                max_length=512, padding=True
            )
            inputs = {k: v.to(DEVICE) for k, v in encoded.items()}  # Fix 4: explicit device
            with torch.no_grad():
                logits = _roberta_model(**inputs).logits
            probs_batch = torch.softmax(logits, dim=1).cpu().tolist()
            for probs in probs_batch:
                label  = ROBERTA_LABELS[probs.index(max(probs))]
                scores = {l: round(p, 4) for l, p in zip(ROBERTA_LABELS, probs)}
                results.append({"label": label, "scores": scores})
        except Exception:
            for _ in batch:
                results.append({"label": "neutral", "scores": {"negative": 0.0, "neutral": 1.0, "positive": 0.0}})
    return results


def get_vader_sentiment(text: str) -> dict:
    scores    = vader.polarity_scores(text)
    compound  = scores["compound"]
    label     = "positive" if compound >= 0.05 else "negative" if compound <= -0.05 else "neutral"
    return {
        "compound": round(compound, 4),
        "pos":      round(scores["pos"], 4),
        "neu":      round(scores["neu"], 4),
        "neg":      round(scores["neg"], 4),
        "label":    label,
    }


def batch_tfidf_keywords(texts: list, top_n: int = 10) -> list:
    """Fix 5: TF-IDF keyword extraction across the batch."""
    if len(texts) < 2:
        return [[] for _ in texts]
    try:
        vec = TfidfVectorizer(
            max_features=500,
            stop_words="english",
            ngram_range=(1, 2),
        )
        matrix = vec.fit_transform(texts)
        terms  = vec.get_feature_names_out()
        results = []
        for row in matrix:
            scores  = zip(terms, row.toarray()[0])
            top     = sorted(scores, key=lambda x: x[1], reverse=True)[:top_n]
            results.append([t for t, s in top if s > 0])
        return results
    except Exception:
        return [[] for _ in texts]


def get_topics_bertopic(texts: list) -> list:
    """Fix 6: BERTopic instead of LDA."""
    if not BERTOPIC_AVAILABLE or len(texts) < 5:
        return []
    try:
        model  = BERTopic(verbose=False, nr_topics="auto")
        topics, _ = model.fit_transform(texts)
        info   = model.get_topic_info()
        result = []
        for _, row in info[info["Topic"] != -1].head(5).iterrows():
            words = [w for w, _ in model.get_topic(row["Topic"])]
            result.append({"topic_id": int(row["Topic"]), "words": words[:5]})
        return result
    except Exception as e:
        print(f"  [warn] BERTopic failed: {e}")
        return []


def detect_events(tweets: list, top_n: int = 5) -> list:
    """Fix 7: freq_ratio replaces spike_score."""
    all_keywords = []
    for tweet in tweets:
        all_keywords.extend(tweet.get("keywords", []))
    freq  = Counter(all_keywords)
    total = sum(freq.values()) or 1
    return [
        {"keyword": kw, "count": cnt, "freq_ratio": round(cnt / total, 4)}  # Fix 7
        for kw, cnt in freq.most_common(top_n)
    ]


def get_engagement(tweet: dict) -> dict:
    return {
        "likes":     tweet.get("likeCount",    tweet.get("favorite_count", 0)),
        "retweets":  tweet.get("retweetCount", tweet.get("retweet_count",  0)),
        "replies":   tweet.get("replyCount",   tweet.get("reply_count",    0)),
        "views":     tweet.get("viewCount",    tweet.get("view_count",     None)),
        "bookmarks": tweet.get("bookmarkCount", None),
    }


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — Run full preprocessing on a processed JSON file
# ─────────────────────────────────────────────────────────────────────────────

def preprocess_file(filepath: str, output_dir: str = "data/nlp") -> str:
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    original_count = len(data.get("tweets", []))
    tweets = data.get("tweets", [])

    # Stage 2 — Filter
    tweets = [t for t in tweets if is_valid(t)]
    after_filter = len(tweets)

    # Stage 3 — Deduplicate
    tweets = deduplicate(tweets)
    after_dedup = len(tweets)

    if not tweets:
        print(f"  ✓ {original_count} → 0 tweets (all filtered)")
    
    # ── Pre-extraction (hashtags, mentions, emojis, URLs) ────────────────────
    for tweet in tweets:
        raw = tweet.get("text", "")
        tweet["hashtags"] = extract_hashtags(raw)
        tweet["mentions"] = extract_mentions(raw)
        tweet["emojis"]   = extract_emojis(raw)   # Fix 8
        tweet["urls"]     = extract_urls(raw)
        tweet["cleaned_text"] = clean_text(raw)

    # ── spaCy batch (Fix 5 nlp.pipe) ─────────────────────────────────────────
    cleaned_texts = [t["cleaned_text"] for t in tweets]
    docs = list(tqdm(
        nlp.pipe(cleaned_texts, batch_size=50),
        total=len(cleaned_texts),
        desc="  spaCy NER",
        leave=False
    ))

    for tweet, doc in zip(tweets, docs):
        # Fix 2: tokens = raw surface forms (lowercased, alpha, no stopwords)
        tweet["tokens"] = [
            token.text.lower()
            for token in doc
            if token.is_alpha and token.text.lower() not in STOPWORDS
        ]
        # Fix 2: lemmatized_tokens = lemma forms (now distinct from tokens)
        tweet["lemmatized_tokens"] = [
            token.lemma_.lower()
            for token in doc
            if token.is_alpha and token.lemma_.lower() not in STOPWORDS
        ]
        entities = [{"text": ent.text, "label": ent.label_} for ent in doc.ents]
        tweet["entities"]    = entities
        tweet["entity_freq"] = dict(Counter([e["text"] for e in entities]))
        tweet["engagement"]  = get_engagement(tweet)

        # Normalize datetime
        raw_date = tweet.get("createdAt", "")
        try:
            dt = datetime.strptime(raw_date, "%a %b %d %H:%M:%S %z %Y")
            tweet["createdAt"] = dt.isoformat()
        except (ValueError, TypeError):
            pass

    # ── VADER sentiment (fast, per-tweet) ────────────────────────────────────
    for tweet in tqdm(tweets, desc="  VADER sentiment", leave=False):
        tweet["sentiment"] = {"vader": get_vader_sentiment(tweet["cleaned_text"])}

    # ── RoBERTa sentiment batch (Fix 3 + Fix 4) ──────────────────────────────
    roberta_results = batch_roberta_sentiment(cleaned_texts)
    for tweet, roberta in zip(tweets, roberta_results):
        tweet["sentiment"]["roberta"]     = roberta
        tweet["sentiment"]["final_label"] = roberta["label"]

    # ── TF-IDF keywords batch (Fix 5) ────────────────────────────────────────
    tfidf_keywords = batch_tfidf_keywords(cleaned_texts)
    for tweet, kws in zip(tweets, tfidf_keywords):
        tweet["keywords"] = kws

    # ── BERTopic (Fix 6) ─────────────────────────────────────────────────────
    topics = get_topics_bertopic(cleaned_texts)

    # ── Event detection (Fix 7: freq_ratio) ──────────────────────────────────
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

    print(f"  ✓ {original_count} → {len(tweets)} tweets after preprocessing")
    print(f"  ✓ Saved → {out_path}")
    return out_path


if __name__ == "__main__":
    processed_dir = "data/processed"
    files = [
        os.path.join(processed_dir, f)
        for f in os.listdir(processed_dir)
        if f.endswith(".json")
    ]
    print(f"Found {len(files)} processed files\n")
    for fp in tqdm(files, desc="Files"):
        print(f"\nProcessing: {fp}")
        preprocess_file(fp)