"""
analysis.py
Reads from pipeline.db and computes structured analysis across all queries.
Outputs: data/analysis/analysis_results.json + printed summary tables.

Run: python analysis.py
"""

import sqlite3
import json
import os
import logging
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

DB_PATH    = "pipeline.db"
OUTPUT_DIR = "data/analysis"
os.makedirs(OUTPUT_DIR, exist_ok=True)


def get_conn():
    if not os.path.exists(DB_PATH):
        raise FileNotFoundError(f"{DB_PATH} not found. Run ingest.py first.")
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ─────────────────────────────────────────────────────────────────────────────
# 1. Sentiment distribution per query
# ─────────────────────────────────────────────────────────────────────────────

def sentiment_by_query(conn) -> list:
    rows = conn.execute("""
        SELECT q.query_text,
               n.final_label,
               COUNT(*) as count
        FROM tweet_nlp n
        JOIN tweets t       ON t.id = n.tweet_id
        JOIN fetch_runs r   ON r.id = t.fetch_run_id
        JOIN queries q      ON q.id = r.query_id
        WHERE n.final_label IS NOT NULL
        GROUP BY q.query_text, n.final_label
        ORDER BY q.query_text, n.final_label
    """).fetchall()

    result = {}
    for row in rows:
        q = row["query_text"]
        if q not in result:
            result[q] = {"positive": 0, "neutral": 0, "negative": 0, "total": 0}
        result[q][row["final_label"]] = row["count"]
        result[q]["total"] += row["count"]

    return result


# ─────────────────────────────────────────────────────────────────────────────
# 2. Top entities per query
# ─────────────────────────────────────────────────────────────────────────────

def top_entities_by_query(conn, top_n=10) -> dict:
    rows = conn.execute("""
        SELECT q.query_text, e.entity_text, e.entity_label,
               SUM(e.frequency) as total_freq
        FROM entities e
        JOIN fetch_runs r ON r.id = e.fetch_run_id
        JOIN queries q    ON q.id = r.query_id
        GROUP BY q.query_text, e.entity_text, e.entity_label
        ORDER BY q.query_text, total_freq DESC
    """).fetchall()

    result = {}
    for row in rows:
        q = row["query_text"]
        if q not in result:
            result[q] = []
        if len(result[q]) < top_n:
            result[q].append({
                "entity": row["entity_text"],
                "label":  row["entity_label"],
                "count":  row["total_freq"]
            })
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 3. Top hashtags per query
# ─────────────────────────────────────────────────────────────────────────────

def top_hashtags_by_query(conn, top_n=10) -> dict:
    rows = conn.execute("""
        SELECT q.query_text, h.hashtag, COUNT(*) as count
        FROM hashtags h
        JOIN fetch_runs r ON r.id = h.fetch_run_id
        JOIN queries q    ON q.id = r.query_id
        GROUP BY q.query_text, h.hashtag
        ORDER BY q.query_text, count DESC
    """).fetchall()

    result = {}
    for row in rows:
        q = row["query_text"]
        if q not in result:
            result[q] = []
        if len(result[q]) < top_n:
            result[q].append({"hashtag": row["hashtag"], "count": row["count"]})
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 4. Top keywords per query
# ─────────────────────────────────────────────────────────────────────────────

def top_keywords_by_query(conn, top_n=10) -> dict:
    rows = conn.execute("""
        SELECT q.query_text, k.keyword, COUNT(*) as count
        FROM keywords k
        JOIN fetch_runs r ON r.id = k.fetch_run_id
        JOIN queries q    ON q.id = r.query_id
        GROUP BY q.query_text, k.keyword
        ORDER BY q.query_text, count DESC
    """).fetchall()

    result = {}
    for row in rows:
        q = row["query_text"]
        if q not in result:
            result[q] = []
        if len(result[q]) < top_n:
            result[q].append({"keyword": row["keyword"], "count": row["count"]})
    return result


# ─────────────────────────────────────────────────────────────────────────────
# 5. Engagement stats per query
# ─────────────────────────────────────────────────────────────────────────────

def engagement_by_query(conn) -> dict:
    rows = conn.execute("""
        SELECT q.query_text,
               COUNT(*)            as tweet_count,
               AVG(n.eng_likes)    as avg_likes,
               AVG(n.eng_retweets) as avg_retweets,
               AVG(n.eng_replies)  as avg_replies,
               AVG(n.eng_views)    as avg_views,
               MAX(n.eng_likes)    as max_likes,
               MAX(n.eng_retweets) as max_retweets
        FROM tweet_nlp n
        JOIN tweets t     ON t.id = n.tweet_id
        JOIN fetch_runs r ON r.id = t.fetch_run_id
        JOIN queries q    ON q.id = r.query_id
        GROUP BY q.query_text
        ORDER BY avg_likes DESC
    """).fetchall()

    return {
        row["query_text"]: {
            "tweet_count":   row["tweet_count"],
            "avg_likes":     round(row["avg_likes"] or 0, 2),
            "avg_retweets":  round(row["avg_retweets"] or 0, 2),
            "avg_replies":   round(row["avg_replies"] or 0, 2),
            "avg_views":     round(row["avg_views"] or 0, 2),
            "max_likes":     row["max_likes"] or 0,
            "max_retweets":  row["max_retweets"] or 0,
        }
        for row in rows
    }


# ─────────────────────────────────────────────────────────────────────────────
# 6. Tweet volume over time per query
# ─────────────────────────────────────────────────────────────────────────────

def tweet_volume_over_time(conn) -> dict:
    rows = conn.execute("""
        SELECT q.query_text, t.created_at, COUNT(*) as count
        FROM tweets t
        JOIN fetch_runs r ON r.id = t.fetch_run_id
        JOIN queries q    ON q.id = r.query_id
        WHERE t.created_at IS NOT NULL
        GROUP BY q.query_text, t.created_at
        ORDER BY q.query_text, t.created_at
    """).fetchall()

    from datetime import datetime as dt
    def parse(s):
        for fmt in ("%a %b %d %H:%M:%S +0000 %Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
            try:
                return dt.strptime(s.strip(), fmt).strftime("%Y-%m-%d")
            except ValueError:
                continue
        return None

    # aggregate by date
    from collections import defaultdict
    buckets = defaultdict(lambda: defaultdict(int))
    for row in rows:
        d = parse(row["created_at"])
        if d:
            buckets[row["query_text"]][d] += row["count"]

    return {
        q: [{"date": d, "count": c} for d, c in sorted(dates.items())]
        for q, dates in buckets.items()
    }


# ─────────────────────────────────────────────────────────────────────────────
# 7. VADER vs RoBERTa agreement rate
# ─────────────────────────────────────────────────────────────────────────────

def sentiment_agreement(conn) -> dict:
    rows = conn.execute("""
        SELECT vader_label, roberta_label, COUNT(*) as count
        FROM tweet_nlp
        WHERE vader_label IS NOT NULL AND roberta_label IS NOT NULL
        GROUP BY vader_label, roberta_label
    """).fetchall()

    total   = sum(r["count"] for r in rows)
    agreed  = sum(r["count"] for r in rows if r["vader_label"] == r["roberta_label"])
    rate    = round(agreed / total * 100, 2) if total > 0 else 0

    return {
        "total_tweets":   total,
        "agreed":         agreed,
        "disagreed":      total - agreed,
        "agreement_rate": rate,
        "breakdown":      [dict(r) for r in rows]
    }


# ─────────────────────────────────────────────────────────────────────────────
# 8. Source distribution
# ─────────────────────────────────────────────────────────────────────────────

def source_distribution(conn) -> dict:
    rows = conn.execute("""
        SELECT source, COUNT(*) as count
        FROM tweets
        WHERE source IS NOT NULL
        GROUP BY source
        ORDER BY count DESC
    """).fetchall()
    return {row["source"]: row["count"] for row in rows}


# ─────────────────────────────────────────────────────────────────────────────
# Print helpers
# ─────────────────────────────────────────────────────────────────────────────

def print_section(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def print_sentiment(sentiment):
    print_section("1. SENTIMENT DISTRIBUTION PER QUERY")
    print(f"{'Query':<35} {'Pos':>6} {'Neu':>6} {'Neg':>6} {'Total':>7}")
    print("-" * 65)
    for q, s in sentiment.items():
        print(f"{q:<35} {s['positive']:>6} {s['neutral']:>6} {s['negative']:>6} {s['total']:>7}")


def print_engagement(engagement):
    print_section("2. ENGAGEMENT STATS PER QUERY")
    print(f"{'Query':<35} {'Tweets':>7} {'AvgLikes':>9} {'AvgRT':>7} {'MaxLikes':>9}")
    print("-" * 70)
    for q, e in engagement.items():
        print(f"{q:<35} {e['tweet_count']:>7} {e['avg_likes']:>9} {e['avg_retweets']:>7} {e['max_likes']:>9}")


def print_top_hashtags(hashtags):
    print_section("3. TOP HASHTAGS PER QUERY (Top 5)")
    for q, tags in hashtags.items():
        print(f"\n  {q}:")
        for h in tags[:5]:
            print(f"    #{h['hashtag']:<30} {h['count']:>5}")


def print_top_keywords(keywords):
    print_section("4. TOP KEYWORDS PER QUERY (Top 5)")
    for q, kws in keywords.items():
        print(f"\n  {q}:")
        for k in kws[:5]:
            print(f"    {k['keyword']:<32} {k['count']:>5}")


def print_agreement(agreement):
    print_section("5. VADER vs RoBERTa AGREEMENT")
    print(f"  Total tweets analysed : {agreement['total_tweets']}")
    print(f"  Agreed                : {agreement['agreed']}")
    print(f"  Disagreed             : {agreement['disagreed']}")
    print(f"  Agreement rate        : {agreement['agreement_rate']}%")


def print_sources(sources):
    print_section("6. SOURCE DISTRIBUTION")
    for src, count in sources.items():
        print(f"  {src:<25} {count:>6} tweets")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("Starting analysis...")
    conn = get_conn()

    sentiment  = sentiment_by_query(conn)
    entities   = top_entities_by_query(conn)
    hashtags   = top_hashtags_by_query(conn)
    keywords   = top_keywords_by_query(conn)
    engagement = engagement_by_query(conn)
    volume     = tweet_volume_over_time(conn)
    agreement  = sentiment_agreement(conn)
    sources    = source_distribution(conn)

    conn.close()

    # Print summaries
    print_sentiment(sentiment)
    print_engagement(engagement)
    print_top_hashtags(hashtags)
    print_top_keywords(keywords)
    print_agreement(agreement)
    print_sources(sources)

    # Save full results to JSON
    results = {
        "generatedAt": datetime.now().isoformat(),
        "sentiment":   sentiment,
        "entities":    entities,
        "hashtags":    hashtags,
        "keywords":    keywords,
        "engagement":  engagement,
        "volume":      volume,
        "agreement":   agreement,
        "sources":     sources,
    }

    out_path = os.path.join(OUTPUT_DIR, "analysis_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    log.info(f"Analysis complete → {out_path}")
    print(f"\n✓ Full results saved to {out_path}")