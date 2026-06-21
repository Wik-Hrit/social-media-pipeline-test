"""
export_csv.py
Converts data/nlp/ JSON files to CSV format.
Groups files by query topic, one CSV per topic.
"""

import json
import os
import csv
import re
from collections import defaultdict


def slugify(filename):
    """Extract topic slug from filename like 'delhi-heatwave_20260618_015310.json'"""
    return re.sub(r'_\d{8}_\d{6}\.json$', '', filename)


def flatten_tweet(tweet):
    """Flatten a tweet dict to a CSV-friendly row."""
    entities = tweet.get("entities", [])
    entity_str = "; ".join([f"{e['text']} ({e['label']})" for e in entities]) if entities else ""

    tokens = tweet.get("tokens", [])
    token_str = ", ".join(tokens[:20]) if tokens else ""  # limit to 20 tokens

    return {
        "id":              tweet.get("id", ""),
        "text":            tweet.get("text", "").replace("\n", " "),
        "cleaned_text":    tweet.get("cleaned_text", "").replace("\n", " "),
        "author":          tweet.get("author", ""),
        "authorFollowers": tweet.get("authorFollowers", ""),
        "createdAt":       tweet.get("createdAt", ""),
        "likeCount":       tweet.get("likeCount", 0),
        "retweetCount":    tweet.get("retweetCount", 0),
        "replyCount":      tweet.get("replyCount", 0),
        "viewCount":       tweet.get("viewCount", 0),
        "lang":            tweet.get("lang", ""),
        "isReply":         tweet.get("isReply", False),
        "hashtags":        ", ".join(tweet.get("hashtags", []) or []),
        "tokens":          token_str,
        "entities":        entity_str,
        "url":             tweet.get("url", ""),
    }


def export_csv(nlp_dir="data/nlp", output_dir="data/csv"):
    os.makedirs(output_dir, exist_ok=True)

    # Group files by topic
    topic_files = defaultdict(list)
    for fname in os.listdir(nlp_dir):
        if fname.endswith(".json"):
            topic = slugify(fname)
            topic_files[topic].append(os.path.join(nlp_dir, fname))

    print(f"Found {len(topic_files)} topics\n")

    for topic, files in sorted(topic_files.items()):
        all_tweets = []

        for fpath in files:
            with open(fpath, encoding="utf-8") as f:
                data = json.load(f)
            tweets = data.get("tweets", [])
            all_tweets.extend(tweets)

        if not all_tweets:
            print(f"  Skipping {topic} — no tweets")
            continue

        # Deduplicate across files
        seen = set()
        unique = []
        for t in all_tweets:
            tid = t.get("id")
            if tid and tid not in seen:
                seen.add(tid)
                unique.append(t)

        out_path = os.path.join(output_dir, f"{topic}.csv")
        rows = [flatten_tweet(t) for t in unique]

        with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)

        print(f"  ✓ {topic} — {len(unique)} tweets → {out_path}")

    print(f"\nDone. CSVs saved to {output_dir}/")


if __name__ == "__main__":
    export_csv()