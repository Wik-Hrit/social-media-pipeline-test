"""
export_csv.py
Exports NLP-enriched tweet data from data/nlp/ to CSVs in data/csv/.
Reads from NLP JSON files (same source as ingest.py).

Usage: python export_csv.py
"""

import os
import sys
import json
import csv
import re
import logging
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)


def flatten_tweet(tweet):
    """Fix 28: Full flatten including all NLP/sentiment fields."""
    entities  = tweet.get("entities", [])
    sentiment = tweet.get("sentiment", {})
    vader     = sentiment.get("vader", {})
    roberta   = sentiment.get("roberta", {})
    eng       = tweet.get("engagement", {})

    entity_str = "; ".join(
        [f"{e['text']} ({e['label']})" for e in entities]
    ) if entities else ""

    tokens    = tweet.get("tokens", [])
    token_str = ", ".join(tokens[:20]) if tokens else ""

    return {
        # ── Base fields ───────────────────────────────────────────────────────
        "id":               tweet.get("id", ""),
        "text":             (tweet.get("text", "") or "").replace("\n", " "),
        "cleaned_text":     (tweet.get("cleaned_text", "") or "").replace("\n", " "),
        "author":           tweet.get("author", ""),
        "authorFollowers":  tweet.get("authorFollowers", ""),
        "createdAt":        tweet.get("createdAt", ""),
        "lang":             tweet.get("lang", ""),
        "isReply":          tweet.get("isReply", False),
        "isRetweet":        tweet.get("isRetweet", False),
        "url":              tweet.get("url", ""),
        # ── Raw engagement ────────────────────────────────────────────────────
        "likeCount":        tweet.get("likeCount", 0),
        "retweetCount":     tweet.get("retweetCount", 0),
        "replyCount":       tweet.get("replyCount", 0),
        "viewCount":        tweet.get("viewCount") or "",
        # ── NLP engagement ────────────────────────────────────────────────────
        "eng_likes":        eng.get("likes", 0),
        "eng_retweets":     eng.get("retweets", 0),
        "eng_replies":      eng.get("replies", 0),
        "eng_views":        eng.get("views") or "",
        "eng_bookmarks":    eng.get("bookmarks") or "",
        # ── Sentiment ─────────────────────────────────────────────────────────
        "final_label":      sentiment.get("final_label", ""),
        "final_confidence": sentiment.get("final_confidence", ""),
        "final_source":     sentiment.get("final_source", ""),
        "vader_compound":   vader.get("compound", ""),
        "vader_label":      vader.get("label", ""),
        "roberta_label":    roberta.get("label", ""),
        # ── NLP tokens / entities / keywords ─────────────────────────────────
        "hashtags":         ", ".join(tweet.get("hashtags", []) or []),
        "keywords":         ", ".join(tweet.get("keywords", []) or []),
        "entities":         entity_str,
        "tokens":           token_str,
    }


def topic_from_filename(fname):
    """
    BUG FIX: Strip timestamp suffix so files are grouped by topic, not by run.

    'climate_change_2024-11-03T14-22-11.json' -> 'climate_change'
    'ai_ethics_20241103_142211.json'           -> 'ai_ethics'
    'bitcoin.json'                             -> 'bitcoin'
    """
    name = os.path.splitext(fname)[0]
    # Strip _YYYY-MM-DD... (ISO date with dashes, with or without time)
    name = re.sub(r'_\d{4}-\d{2}-\d{2}.*$', '', name)
    # Strip _YYYYMMDD... (compact date, no dashes)
    name = re.sub(r'_\d{8}.*$', '', name)
    return name


def export_csv(nlp_dir="data/nlp", output_dir="data/csv"):
    if not os.path.exists(nlp_dir):
        log.error(f"{nlp_dir} not found. Run preprocess.py first.")
        return

    os.makedirs(output_dir, exist_ok=True)
    topic_files = defaultdict(list)

    for root, dirs, filenames in os.walk(nlp_dir):
        for fname in filenames:
            if fname.endswith(".json"):
                # BUG FIX: was slugify(fname) which kept the timestamp,
                # producing one CSV per fetch run (148) instead of per topic (24)
                topic = topic_from_filename(fname)
                topic_files[topic].append(os.path.join(root, fname))

    if not topic_files:
        log.warning(f"No JSON files found under {nlp_dir}")
        return

    log.info(f"Found {len(topic_files)} unique topics across all NLP files")

    total_rows = 0
    for topic, files in sorted(topic_files.items()):
        rows = []
        seen_ids = set()
        for fpath in files:
            try:
                with open(fpath, encoding="utf-8") as f:
                    data = json.load(f)
                for tweet in data.get("tweets", []):
                    tid = tweet.get("id")
                    if tid and tid not in seen_ids:
                        seen_ids.add(tid)
                        rows.append(flatten_tweet(tweet))
            except Exception as e:
                log.error(f"  Error reading {fpath}: {e}")

        if not rows:
            continue

        out_path = os.path.join(output_dir, f"{topic}.csv")
        fieldnames = list(rows[0].keys())
        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        log.info(f"  ✓ {topic[:40]:<40} {len(rows):>5} rows → {out_path}")
        total_rows += len(rows)

    log.info(f"\n✓ Export complete — {total_rows:,} total rows across {len(topic_files)} topics → {output_dir}/")


if __name__ == "__main__":
    export_csv()