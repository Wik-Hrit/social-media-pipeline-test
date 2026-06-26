"""
preprocess.py
Preprocessing pipeline for collected tweet data.
Stages:
    1. Text cleaning (with emoji preservation, URL storage, hashtag/mention extraction)
    2. Filtering (retweets, language, empty)
    3. Deduplication (ID + text-based)
    4. NLP enrichment (tokens, lemmatization, stopwords, NER, entity freq,
                       sentiment, keywords, topic modelling, engagement metrics)
"""

import re
import json
import os
from collections import Counter
from datetime import datetime

from langdetect import detect, LangDetectException
from langdetect import DetectorFactory
DetectorFactory.seed = 0                          # Fix 7: deterministic langdetect

import nltk
from nltk.corpus import stopwords
from nltk.tokenize import word_tokenize
nltk.download("punkt",     quiet=True)
nltk.download("punkt_tab", quiet=True)
nltk.download("stopwords", quiet=True)
nltk.download("wordnet",   quiet=True)
from nltk.stem import WordNetLemmatizer

import spacy
# Fix 10: Sentiment — VADER + RoBERTa (twitter-trained)
from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
from transformers import AutoTokenizer, AutoModelForSequenceClassification
import torch

vader = SentimentIntensityAnalyzer()
ROBERTA_MODEL      = "cardiffnlp/twitter-roberta-base-sentiment"
_roberta_tokenizer = AutoTokenizer.from_pretrained(ROBERTA_MODEL)
_roberta_model     = AutoModelForSequenceClassification.from_pretrained(ROBERTA_MODEL)
_roberta_model.eval()
ROBERTA_LABELS = ["negative", "neutral", "positive"]

# Fix 13: Topic Modelling via LDA
from gensim import corpora
from gensim.models import LdaModel

# ── Models ────────────────────────────────────────────────────────────────────
nlp        = spacy.load("en_core_web_sm")
STOPWORDS  = set(stopwords.words("english"))
lemmatizer = WordNetLemmatizer()


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

EMOJI_PATTERN = re.compile(
    "["
    u"\U0001F600-\U0001F64F"
    u"\U0001F300-\U0001F5FF"
    u"\U0001F680-\U0001F9FF"
    u"\U00002700-\U000027BF"
    u"\U0001FA00-\U0001FA6F"
    "]+",
    flags=re.UNICODE,
)

def extract_hashtags(text: str) -> list:
    """Fix 1: Extract hashtags from raw text."""
    return re.findall(r"#(\w+)", text)

def extract_mentions(text: str) -> list:
    """Fix 2: Extract @mentions from raw text."""
    return re.findall(r"@(\w+)", text)

def extract_urls(text: str) -> list:
    """Fix 4: Store URLs before removing them."""
    return re.findall(r"http\S+|www\S+", text)

def extract_emojis(text: str) -> list:
    """Fix 3: Extract emojis before cleaning."""
    return EMOJI_PATTERN.findall(text)


# ─────────────────────────────────────────────────────────────────────────────
# STAGE 1 — Text Cleaning
# ─────────────────────────────────────────────────────────────────────────────

def clean_text(text: str) -> str:
    """Remove URLs, mentions, hashtag symbols, collapse whitespace.
    Emojis are preserved in a separate field, not stripped here."""
    if not text:
        return ""
    text = re.sub(r"http\S+|www\S+", "", text)   # remove URLs
    text = re.sub(r"@\w+", "", text)              # remove @mentions
    text = re.sub(r"#(\w+)", r"\1", text)         # strip # but keep word
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
# STAGE 3 — Deduplication  (Fix 8: ID + text dedup)
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
# STAGE 4 — NLP Enrichment
# ─────────────────────────────────────────────────────────────────────────────

def get_sentiment(text: str) -> dict:
    """Fix 10: VADER (fast, compound score) + RoBERTa (tweet-trained, accurate)."""
    # VADER
    vader_scores = vader.polarity_scores(text)
    compound     = vader_scores["compound"]
    vader_label  = "positive" if compound >= 0.05 else "negative" if compound <= -0.05 else "neutral"

    # RoBERTa — truncate to 512 tokens
    try:
        inputs  = _roberta_tokenizer(text, return_tensors="pt", truncation=True, max_length=512)
        with torch.no_grad():
            logits = _roberta_model(**inputs).logits
        probs        = torch.softmax(logits, dim=1).squeeze().tolist()
        roberta_label = ROBERTA_LABELS[probs.index(max(probs))]
        roberta_scores = {label: round(p, 4) for label, p in zip(ROBERTA_LABELS, probs)}
    except Exception:
        roberta_label  = "neutral"
        roberta_scores = {"negative": 0.0, "neutral": 1.0, "positive": 0.0}

    return {
        "vader": {
            "compound": round(compound, 4),
            "pos":      round(vader_scores["pos"], 4),
            "neu":      round(vader_scores["neu"], 4),
            "neg":      round(vader_scores["neg"], 4),
            "label":    vader_label,
        },
        "roberta": {
            "label":  roberta_label,
            "scores": roberta_scores,
        },
        "final_label": roberta_label,   # RoBERTa as primary signal
    }

def get_keywords(tokens: list, top_n: int = 10) -> list:
    """Fix 11: Top-N keywords by frequency."""
    return [w for w, _ in Counter(tokens).most_common(top_n)]

def get_topics(all_tokens: list, num_topics: int = 5, num_words: int = 5) -> list:
    """Fix 13: LDA topic modelling across all tweets in a file.
    Returns list of topics, each with top words."""
    if len(all_tokens) < 2:
        return []
    dictionary = corpora.Dictionary(all_tokens)
    dictionary.filter_extremes(no_below=2, no_above=0.9)
    corpus = [dictionary.doc2bow(tokens) for tokens in all_tokens]
    if not any(corpus):
        return []
    lda = LdaModel(
        corpus=corpus,
        id2word=dictionary,
        num_topics=num_topics,
        random_state=42,
        passes=5,
    )
    topics = []
    for idx, topic in lda.show_topics(num_topics=num_topics, num_words=num_words, formatted=False):
        topics.append({
            "topic_id": idx,
            "words": [w for w, _ in topic],
        })
    return topics


def detect_events(tweets: list, top_n: int = 5) -> list:
    """Fix 12: Simple keyword-spike event detection.
    Finds top-N keywords that spike across the tweet batch — signals an event."""
    all_keywords = []
    for tweet in tweets:
        all_keywords.extend(tweet.get("keywords", []))
    freq = Counter(all_keywords)
    total = sum(freq.values()) or 1
    events = [
        {"keyword": kw, "count": cnt, "spike_score": round(cnt / total, 4)}
        for kw, cnt in freq.most_common(top_n)
    ]
    return events


def get_engagement(tweet: dict) -> dict:
    """Fix 15: Collect engagement metrics."""
    return {
        "likes":       tweet.get("likeCount",    tweet.get("favorite_count", 0)),
        "retweets":    tweet.get("retweetCount", tweet.get("retweet_count",  0)),
        "replies":     tweet.get("replyCount",   tweet.get("reply_count",    0)),
        "views":       tweet.get("viewCount",    tweet.get("view_count",     None)),
        "bookmarks":   tweet.get("bookmarkCount", None),
    }


def enrich(tweet: dict) -> dict:
    raw_text = tweet.get("text", "")

    # ── Pre-extraction (before cleaning) ──────────────────────────────────────
    tweet["hashtags"] = extract_hashtags(raw_text)   # Fix 1
    tweet["mentions"] = extract_mentions(raw_text)   # Fix 2
    tweet["emojis"]   = extract_emojis(raw_text)     # Fix 3
    tweet["urls"]     = extract_urls(raw_text)        # Fix 4

    # ── Cleaned text ──────────────────────────────────────────────────────────
    text = clean_text(raw_text)
    tweet["cleaned_text"] = text

    # ── spaCy batch via nlp.pipe (Fix 5) ─────────────────────────────────────
    doc = nlp(text)

    # Fix 6 + 14: spaCy tokenization + lemmatization
    tokens = [
        token.lemma_.lower()
        for token in doc
        if token.is_alpha and token.lemma_.lower() not in STOPWORDS
    ]
    tweet["tokens"]           = tokens              # lemmatized (Fix 14)
    tweet["lemmatized_tokens"]= tokens              # alias for clarity

    # Fix 9: NER with entity frequency
    entities = [{"text": ent.text, "label": ent.label_} for ent in doc.ents]
    tweet["entities"]      = entities
    entity_texts           = [e["text"] for e in entities]
    tweet["entity_freq"]   = dict(Counter(entity_texts))   # Fix 9

    # Fix 10: Sentiment
    tweet["sentiment"] = get_sentiment(text)

    # Fix 11: Keywords
    tweet["keywords"] = get_keywords(tokens)

    # Fix 15: Engagement metrics
    tweet["engagement"] = get_engagement(tweet)

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
    with open(filepath, encoding="utf-8") as f:
        data = json.load(f)

    original_count = len(data.get("tweets", []))
    tweets = data.get("tweets", [])

    # Stage 1+2 — Clean and filter
    tweets = [t for t in tweets if is_valid(t)]
    after_filter = len(tweets)

    # Stage 3 — Deduplicate (ID + text)
    tweets = deduplicate(tweets)
    after_dedup = len(tweets)

    # Stage 4 — NLP enrichment via batch pipe (Fix 5)
    texts  = [clean_text(t.get("text", "")) for t in tweets]
    docs   = list(nlp.pipe(texts, batch_size=50))
    for tweet, doc in zip(tweets, docs):
        raw_text = tweet.get("text", "")
        tweet["hashtags"] = extract_hashtags(raw_text)
        tweet["mentions"] = extract_mentions(raw_text)
        tweet["emojis"]   = extract_emojis(raw_text)
        tweet["urls"]     = extract_urls(raw_text)
        text = clean_text(raw_text)
        tweet["cleaned_text"] = text
        tokens = [
            token.lemma_.lower()
            for token in doc
            if token.is_alpha and token.lemma_.lower() not in STOPWORDS
        ]
        tweet["tokens"]            = tokens
        tweet["lemmatized_tokens"] = tokens
        entities = [{"text": ent.text, "label": ent.label_} for ent in doc.ents]
        tweet["entities"]   = entities
        tweet["entity_freq"] = dict(Counter([e["text"] for e in entities]))
        tweet["sentiment"]  = get_sentiment(text)
        tweet["keywords"]   = get_keywords(tokens)
        tweet["engagement"] = get_engagement(tweet)
        raw_date = tweet.get("createdAt", "")
        try:
            dt = datetime.strptime(raw_date, "%a %b %d %H:%M:%S %z %Y")
            tweet["createdAt"] = dt.isoformat()
        except (ValueError, TypeError):
            pass

    # Fix 13: Topic modelling across all tweets
    all_tokens = [t.get("tokens", []) for t in tweets]
    topics = get_topics(all_tokens)

    # Fix 12: Event detection via keyword spikes
    events = detect_events(tweets)

    result = {
        "metadata": {
            **data.get("metadata", {}),
            "preprocessedAt": datetime.now().isoformat(),
            "originalCount":  original_count,
            "afterFilter":    after_filter,
            "afterDedup":     after_dedup,
            "finalCount":     len(tweets),
        },
        "topics":  topics,   # Fix 13
        "events":  events,   # Fix 12
        "tweets":  tweets,
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
    for fp in files:
        print(f"Processing: {fp}")
        preprocess_file(fp)
        print()