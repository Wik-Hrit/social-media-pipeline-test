"""
ingest.py
One-time migration — reads all data/processed/ and data/nlp/ JSON files
and inserts everything into pipeline.db (9 tables).

Safe to re-run: already_ingested set prevents duplicate fetch_runs.

Usage:
    python ingest.py
"""

import json
import os
import logging
from db_manager import (
    init_db, get_conn,
    upsert_query, insert_fetch_run,
    insert_tweets, insert_nlp,
    insert_entities, insert_hashtags, insert_keywords,
    insert_topics, insert_events,
    DB_PATH
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

PROCESSED_DIR = "data/processed"
NLP_DIR       = "data/nlp"


def load_json(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def get_all_json_files(directory: str) -> dict:
    """Walk ALL subdirectories. Returns {filename: full_path}."""
    file_map = {}
    for root, dirs, filenames in os.walk(directory):
        for fname in filenames:
            if fname.endswith(".json"):
                if fname in file_map:
                    # I2: warn on filename collision
                    log.warning(f"Duplicate filename '{fname}' — keeping first occurrence")
                else:
                    file_map[fname] = os.path.join(root, fname)
    return file_map


def ingest_all():
    init_db()

    processed_map = get_all_json_files(PROCESSED_DIR)
    nlp_map       = get_all_json_files(NLP_DIR)

    log.info(f"Found {len(processed_map)} processed files")
    log.info(f"Found {len(nlp_map)} NLP files")

    # I3: build already_ingested set before loop — prevents duplicate runs
    with get_conn() as conn:
        rows = conn.execute("SELECT nlp_file FROM fetch_runs WHERE nlp_file IS NOT NULL").fetchall()
        already_ingested = {row["nlp_file"] for row in rows}
    log.info(f"Already ingested: {len(already_ingested)} files — will skip")

    total_tweets   = 0
    total_nlp      = 0
    total_entities = 0
    total_hashtags = 0
    total_keywords = 0
    total_files    = len(processed_map)

    for i, (fname, processed_path) in enumerate(sorted(processed_map.items()), 1):
        # I3: skip already ingested
        if fname in already_ingested:
            log.info(f"[{i}/{total_files}] Skipping (already ingested): {fname}")
            continue

        nlp_path = nlp_map.get(fname)
        # I1: progress counter
        log.info(f"\n[{i}/{total_files}] Ingesting: {fname}")

        # I1: wrap each file in try/except — one bad JSON won't crash entire ingestion
        try:
            processed_data = load_json(processed_path)
        except Exception as e:
            log.error(f"  Failed to load {processed_path}: {e} — skipping")
            continue

        try:
            nlp_data = load_json(nlp_path) if nlp_path else None
        except Exception as e:
            log.warning(f"  Failed to load NLP file {nlp_path}: {e} — NLP skipped")
            nlp_data = None

        meta   = processed_data.get("metadata", {})
        query  = meta.get("query", "unknown")
        tweets = processed_data.get("tweets", [])

        if nlp_data:
            meta = {**meta, **nlp_data.get("metadata", {})}

        with get_conn() as conn:
            query_id = upsert_query(conn, query)
            run_id   = insert_fetch_run(
                conn, query_id, meta,
                processed_file=fname,
                nlp_file=fname if nlp_path else None
            )

            n_tweets = insert_tweets(conn, run_id, tweets, default_source=meta.get("apiSource"))
            total_tweets += n_tweets
            log.info(f"  ✓ {n_tweets} tweets")

            n_ht = insert_hashtags(conn, run_id, tweets)
            total_hashtags += n_ht
            log.info(f"  ✓ {n_ht} hashtags")

            if nlp_data:
                nlp_tweets = nlp_data.get("tweets", [])
                n_nlp      = insert_nlp(conn, run_id, nlp_tweets)
                total_nlp += n_nlp
                n_ent      = insert_entities(conn, run_id, nlp_tweets)
                total_entities += n_ent
                n_kw       = insert_keywords(conn, run_id, nlp_tweets)
                total_keywords += n_kw
                n_topics   = insert_topics(conn, run_id, nlp_data.get("topics", []))
                n_events   = insert_events(conn, run_id, nlp_data.get("events", []))
                log.info(f"  ✓ {n_nlp} NLP | {n_ent} entities | {n_kw} keywords | "
                         f"{n_topics} topics | {n_events} events")
            else:
                log.warning(f"  No NLP file found for {fname} — NLP tables skipped")

    log.info(f"\n{'='*55}")
    log.info(f"Ingestion complete.")
    log.info(f"  Tweets    : {total_tweets}")
    log.info(f"  NLP rows  : {total_nlp}")
    log.info(f"  Entities  : {total_entities}")
    log.info(f"  Hashtags  : {total_hashtags}")
    log.info(f"  Keywords  : {total_keywords}")
    log.info(f"  Database  : {DB_PATH}")


if __name__ == "__main__":
    ingest_all()