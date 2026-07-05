"""
verify_db.py — Quick sanity check for pipeline.db
Prints row counts for all 9 tables.
"""
import sqlite3
import os

DB_PATH = "pipeline.db"

# V1: existence check — don't silently create blank DB
if not os.path.exists(DB_PATH):
    print(f"ERROR: {DB_PATH} not found. Run ingest.py first.")
    exit(1)

tables = [
    "queries", "fetch_runs", "tweets", "tweet_nlp",
    "entities", "hashtags", "keywords", "topics", "events"
]

# V2: use context manager — no connection leak on error
with sqlite3.connect(DB_PATH) as conn:
    print(f"\n{'Table':<15} {'Rows':>8}")
    print("-" * 25)
    for t in tables:
        try:
            count = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"{t:<15} {count:>8,}")
        except Exception as e:
            print(f"{t:<15} ERROR: {e}")
    print()