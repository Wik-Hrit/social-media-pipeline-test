"""
verify_db.py
Quick sanity check — row counts for all 9 tables + entity label breakdown.
Run: python verify_db.py
"""

import sqlite3
import os
import sys
from config import DB_PATH   # Fix 19+23


def main():
    if not os.path.exists(DB_PATH):
        print(f"ERROR: {DB_PATH} not found.")
        sys.exit(1)

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row

        print(f"\nDB: {DB_PATH}")
        print("─" * 35)
        tables = ["queries","fetch_runs","tweets","tweet_nlp",
                  "entities","hashtags","keywords","topics","events"]
        for t in tables:
            try:
                c = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                print(f"  {t:<15} {c:>8,}")
            except Exception as e:
                print(f"  {t:<15} ERROR: {e}")

        print("\nNER Label Distribution:")
        print("─" * 35)
        rows = conn.execute("""
            SELECT entity_label, COUNT(*) as cnt
            FROM entities GROUP BY entity_label ORDER BY cnt DESC
        """).fetchall()
        for r in rows:
            print(f"  {r['entity_label']:<10} {r['cnt']:>7,}")
        print()


if __name__ == "__main__":   # Fix 9
    main()