"""
pipeline_stats.py
One-command health dashboard for the Social Media NLP Pipeline.
Reads directly from pipeline.db and prints a full status report.

Run: python pipeline_stats.py
"""

import sqlite3
import os
import sys
from datetime import datetime

DB_PATH = "pipeline.db"

if not os.path.exists(DB_PATH):
    print(f"ERROR: {DB_PATH} not found. Run ingest.py first.")
    sys.exit(1)


def sep(title=""):
    if title:
        print(f"\n{'─'*20} {title} {'─'*(35-len(title))}")
    else:
        print("─" * 58)


with sqlite3.connect(DB_PATH) as conn:
    conn.row_factory = sqlite3.Row

    print("\n" + "="*58)
    print("   SOCIAL MEDIA NLP PIPELINE — HEALTH DASHBOARD")
    print(f"   Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("="*58)

    # ── 1. Table counts ───────────────────────────────────────
    sep("DB OVERVIEW")
    tables = ["queries","fetch_runs","tweets","tweet_nlp",
              "entities","hashtags","keywords","topics","events"]
    for t in tables:
        c = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:<15} {c:>8,}")

    # ── 2. Query coverage ─────────────────────────────────────
    sep("QUERY COVERAGE")
    rows = conn.execute("""
        SELECT q.query_text, COUNT(DISTINCT t.id) as tweets
        FROM queries q
        LEFT JOIN fetch_runs r ON r.query_id = q.id
        LEFT JOIN tweets t     ON t.fetch_run_id = r.id
        GROUP BY q.query_text
        ORDER BY tweets DESC
    """).fetchall()
    for r in rows:
        bar = "█" * min(30, r["tweets"] // 5)
        print(f"  {r['query_text'][:30]:<30} {r['tweets']:>4}  {bar}")

    # ── 3. Sentiment summary ──────────────────────────────────
    sep("SENTIMENT SUMMARY")
    s = conn.execute("""
        SELECT final_label, COUNT(*) as cnt
        FROM tweet_nlp
        WHERE final_label IS NOT NULL
        GROUP BY final_label
    """).fetchall()
    total_nlp = sum(r["cnt"] for r in s)
    for r in s:
        pct = r["cnt"] / total_nlp * 100 if total_nlp else 0
        print(f"  {r['final_label']:<10} {r['cnt']:>6,}  ({pct:.1f}%)")

    # ── 4. VADER vs RoBERTa agreement ────────────────────────
    sep("MODEL AGREEMENT")
    ag = conn.execute("""
        SELECT COUNT(*) as total,
               SUM(CASE WHEN vader_label = roberta_label THEN 1 ELSE 0 END) as agreed
        FROM tweet_nlp
        WHERE vader_label IS NOT NULL AND roberta_label IS NOT NULL
    """).fetchone()
    if ag["total"]:
        rate = ag["agreed"] / ag["total"] * 100
        print(f"  VADER vs RoBERTa agreement : {rate:.1f}%")
        print(f"  Agreed  : {ag['agreed']:,}  |  Disagreed: {ag['total']-ag['agreed']:,}")

    # ── 5. Top 10 entities ────────────────────────────────────
    sep("TOP 10 ENTITIES")
    ents = conn.execute("""
        SELECT entity_text, entity_label, SUM(frequency) as freq
        FROM entities
        GROUP BY entity_text, entity_label
        ORDER BY freq DESC LIMIT 10
    """).fetchall()
    for e in ents:
        print(f"  {e['entity_text'][:25]:<25} [{e['entity_label']:<10}] {e['freq']:>5,}")

    # ── 6. Entity label distribution ─────────────────────────
    sep("ENTITY LABELS")
    elabels = conn.execute("""
        SELECT entity_label, COUNT(*) as cnt
        FROM entities GROUP BY entity_label ORDER BY cnt DESC
    """).fetchall()
    for r in elabels:
        print(f"  {r['entity_label']:<15} {r['cnt']:>7,}")

    # ── 7. Engagement leaders ─────────────────────────────────
    sep("ENGAGEMENT LEADERS (avg likes)")
    eng = conn.execute("""
        SELECT q.query_text, AVG(n.eng_likes) as avg_likes,
               AVG(n.eng_retweets) as avg_rt, AVG(n.eng_views) as avg_views
        FROM tweet_nlp n
        JOIN tweets t     ON t.id = n.tweet_id
        JOIN fetch_runs r ON r.id = t.fetch_run_id
        JOIN queries q    ON q.id = r.query_id
        GROUP BY q.query_text ORDER BY avg_likes DESC LIMIT 5
    """).fetchall()
    print(f"  {'Query':<30} {'AvgLikes':>9} {'AvgRT':>7} {'AvgViews':>10}")
    print(f"  {'-'*58}")
    for r in eng:
        print(f"  {r['query_text'][:30]:<30} {r['avg_likes'] or 0:>9.1f} "
              f"{r['avg_rt'] or 0:>7.1f} {r['avg_views'] or 0:>10.1f}")

    # ── 8. Most active fetch runs ─────────────────────────────
    sep("RECENT FETCH RUNS (top 5 by tweets)")
    runs = conn.execute("""
        SELECT q.query_text, r.fetched_at, r.final_count
        FROM fetch_runs r
        JOIN queries q ON q.id = r.query_id
        WHERE r.final_count IS NOT NULL
        ORDER BY r.final_count DESC LIMIT 5
    """).fetchall()
    for r in runs:
        print(f"  {r['query_text'][:28]:<28} {r['final_count']:>4} tweets  {r['fetched_at'] or ''[:10]}")

    sep()
    print(f"  Pipeline DB: {os.path.abspath(DB_PATH)}")
    print(f"  DB size    : {os.path.getsize(DB_PATH) / 1024 / 1024:.2f} MB")
    print("="*58 + "\n")