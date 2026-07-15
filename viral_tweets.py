"""
viral_tweets.py
Flags tweets where eng_likes > mean + 2*std per query.

Also flags by retweets and views using the same threshold.
Outputs a ranked table to stdout + saves data/analysis/viral_tweets.json.

Usage: python viral_tweets.py
"""

import os
import sys
import json
import logging
import sqlite3
from datetime import datetime
from collections import defaultdict
from config import DB_PATH

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

OUTPUT_PATH = "data/analysis/viral_tweets.json"
os.makedirs("data/analysis", exist_ok=True)

if not os.path.exists(DB_PATH):
    log.error(f"{DB_PATH} not found. Run ingest.py first.")
    sys.exit(1)


def mean_std(values):
    if not values:
        return 0.0, 0.0
    n   = len(values)
    mu  = sum(values) / n
    var = sum((v - mu) ** 2 for v in values) / n
    return mu, var ** 0.5


def detect_viral(conn):
    """
    For each query, compute per-metric (likes, retweets, views) thresholds
    as mean + 2*std across all tweets for that query.
    A tweet is viral if it exceeds ANY one threshold.
    """
    # Pull all tweets with their engagement + query label
    rows = conn.execute("""
        SELECT
            t.id, t.text, t.author, t.created_at, t.url,
            n.eng_likes, n.eng_retweets, n.eng_views,
            n.final_label,
            q.query_text AS query
        FROM tweet_nlp n
        JOIN tweets t      ON n.tweet_id      = t.id
        JOIN fetch_runs fr ON n.fetch_run_id  = fr.id
        JOIN queries q     ON fr.query_id     = q.id
    """).fetchall()

    # Group by query
    by_query = defaultdict(list)
    for r in rows:
        by_query[r["query"]].append(dict(r))

    viral_all = []

    for query, tweets in by_query.items():
        likes_vals    = [t["eng_likes"]    or 0 for t in tweets]
        rt_vals       = [t["eng_retweets"] or 0 for t in tweets]
        views_vals    = [t["eng_views"]    or 0 for t in tweets]

        mu_l, sd_l = mean_std(likes_vals)
        mu_r, sd_r = mean_std(rt_vals)
        mu_v, sd_v = mean_std(views_vals)

        thresh_likes = mu_l + 2 * sd_l
        thresh_rt    = mu_r + 2 * sd_r
        thresh_views = mu_v + 2 * sd_v

        for t in tweets:
            likes    = t["eng_likes"]    or 0
            retweets = t["eng_retweets"] or 0
            views    = t["eng_views"]    or 0

            flags = []
            if likes    > thresh_likes and thresh_likes > 0: flags.append("likes")
            if retweets > thresh_rt    and thresh_rt    > 0: flags.append("retweets")
            if views    > thresh_views and thresh_views > 0: flags.append("views")

            if flags:
                viral_all.append({
                    "query":         query,
                    "tweet_id":      t["id"],
                    "author":        t["author"],
                    "text":          (t["text"] or "")[:200],
                    "created_at":    t["created_at"],
                    "url":           t["url"],
                    "eng_likes":     likes,
                    "eng_retweets":  retweets,
                    "eng_views":     views,
                    "sentiment":     t["final_label"],
                    "viral_by":      flags,
                    "likes_threshold":    round(thresh_likes, 1),
                    "retweets_threshold": round(thresh_rt,    1),
                    "views_threshold":    round(thresh_views, 1),
                    "likes_zscore":  round((likes    - mu_l) / sd_l, 2) if sd_l > 0 else None,
                    "rt_zscore":     round((retweets - mu_r) / sd_r, 2) if sd_r > 0 else None,
                })

    # Sort by likes descending
    viral_all.sort(key=lambda x: x["eng_likes"], reverse=True)
    return viral_all


def print_table(viral):
    if not viral:
        print("No viral tweets detected.")
        return

    print(f"\n{'─'*22} VIRAL TWEETS {'─'*22}")
    print(f"  Threshold: mean + 2σ per metric per query")
    print(f"  Total flagged: {len(viral)}\n")

    # Group by query for display
    by_q = defaultdict(list)
    for t in viral:
        by_q[t["query"]].append(t)

    for query, tweets in sorted(by_q.items()):
        print(f"  ▸ {query}  ({len(tweets)} viral)")
        for t in tweets[:5]:   # top 5 per query in stdout
            flags = "+".join(t["viral_by"])
            text_snippet = t["text"][:80].replace("\n", " ")
            print(f"    [{flags}]  @{t['author']}  ❤ {t['eng_likes']:,}  🔁 {t['eng_retweets']:,}")
            print(f"    \"{text_snippet}...\"")
        if len(tweets) > 5:
            print(f"    ... and {len(tweets)-5} more (see viral_tweets.json)")
        print()


def main():
    log.info(f"Connecting to {DB_PATH} ...")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    log.info("Computing per-query viral thresholds (mean + 2σ) ...")
    viral = detect_viral(conn)
    conn.close()

    print_table(viral)

    output = {
        "generated_at": datetime.now().isoformat(),
        "total_viral":  len(viral),
        "threshold_method": "mean + 2*std per metric per query",
        "tweets": viral,
    }
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    log.info(f"✓ Saved → {OUTPUT_PATH}  ({len(viral)} viral tweets)")
    print(f"✓ Full results → {OUTPUT_PATH}")


if __name__ == "__main__":
    main()