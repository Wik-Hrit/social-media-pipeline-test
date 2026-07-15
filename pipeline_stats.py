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
from config import DB_PATH   # Fix 19+23


def sep(title=""):
    if title:
        print(f"\n{'─'*58}")
        print(f"  {title}")
        print("─" * 58)
    else:
        print("─" * 58)


def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found. Run ingest.py first.")
        sys.exit(1)

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
            GROUP BY q.id ORDER BY tweets DESC
        """).fetchall()
        for r in rows:
            print(f"  {r['query_text'][:35]:<35} {r['tweets']:>5} tweets")

        # ── 3. Sentiment summary ──────────────────────────────────
        sep("SENTIMENT SUMMARY")
        sent = conn.execute("""
            SELECT final_label, COUNT(*) as cnt
            FROM tweet_nlp WHERE final_label IS NOT NULL
            GROUP BY final_label
        """).fetchall()
        total_sent = sum(r['cnt'] for r in sent)
        for r in sent:
            pct = r['cnt'] / total_sent * 100 if total_sent else 0
            print(f"  {r['final_label']:<12} {r['cnt']:>6,}  ({pct:.1f}%)")

        # ── 4. Model agreement ────────────────────────────────────
        sep("VADER vs ROBERTA AGREEMENT")
        agree = conn.execute("""
            SELECT
                SUM(CASE WHEN vader_label = roberta_label THEN 1 ELSE 0 END) as agreed,
                COUNT(*) as total
            FROM tweet_nlp WHERE vader_label IS NOT NULL AND roberta_label IS NOT NULL
        """).fetchone()
        if agree and agree['total']:
            rate = agree['agreed'] / agree['total'] * 100
            print(f"  Agreed    : {agree['agreed']:,} / {agree['total']:,}  ({rate:.1f}%)")
            print(f"  Disagreed : {agree['total'] - agree['agreed']:,}")

        # ── 5. Top entities ───────────────────────────────────────
        sep("TOP ENTITIES (by frequency)")
        ents = conn.execute("""
            SELECT entity_text, entity_label, SUM(frequency) as freq
            FROM entities GROUP BY entity_text, entity_label
            ORDER BY freq DESC LIMIT 10
        """).fetchall()
        for e in ents:
            print(f"  {e['entity_text'][:25]:<25} [{e['entity_label']:<6}] {e['freq']:>5}")

        # ── 6. NER label distribution ─────────────────────────────
        sep("NER LABEL DISTRIBUTION")
        ner = conn.execute("""
            SELECT entity_label, COUNT(*) as cnt
            FROM entities GROUP BY entity_label ORDER BY cnt DESC
        """).fetchall()
        for r in ner:
            print(f"  {r['entity_label']:<10} {r['cnt']:>7,}")

        # ── 7. Engagement leaders ─────────────────────────────────
        sep("TOP TWEETS BY LIKES")
        top_tweets = conn.execute("""
            SELECT t.author, t.text, n.eng_likes, q.query_text
            FROM tweet_nlp n
            JOIN tweets t ON n.tweet_id = t.id
            JOIN fetch_runs fr ON n.fetch_run_id = fr.id
            JOIN queries q ON fr.query_id = q.id
            WHERE n.eng_likes IS NOT NULL
            ORDER BY n.eng_likes DESC LIMIT 5
        """).fetchall()
        for t in top_tweets:
            snippet = (t['text'] or '')[:50].replace('\n', ' ')
            print(f"  @{t['author']:<15} ❤ {t['eng_likes']:>6}  [{t['query_text'][:20]}]")
            print(f"    \"{snippet}...\"")

        # ── 8. Recent fetch runs ──────────────────────────────────
        sep("RECENT FETCH RUNS (top 5 by tweets)")
        runs = conn.execute("""
            SELECT q.query_text, r.fetched_at, r.final_count
            FROM fetch_runs r
            JOIN queries q ON q.id = r.query_id
            WHERE r.final_count IS NOT NULL
            ORDER BY r.final_count DESC LIMIT 5
        """).fetchall()
        for r in runs:
            print(f"  {r['query_text'][:28]:<28} {r['final_count']:>4} tweets")

        sep()
        print(f"  Pipeline DB: {os.path.abspath(DB_PATH)}")
        print(f"  DB size    : {os.path.getsize(DB_PATH) / 1024 / 1024:.2f} MB")
        print("="*58 + "\n")


if __name__ == "__main__":   # Fix 9
    main()