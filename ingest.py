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

try:
    from bertopic import BERTopic
    BERTOPIC_AVAILABLE = True
except ImportError:
    BERTOPIC_AVAILABLE = False
    log.warning("BERTopic not installed — per-query topic modelling disabled.")


def get_topics_bertopic(texts: list, top_n: int = 10) -> list:
    """
    Fix 3: BERTopic per QUERY, not per file.

    Called once per query on ALL cleaned tweet text pooled across every
    fetch_run for that query (previously this ran separately on each
    small per-file batch in preprocess.py, which starved BERTopic of
    data and produced noisy, redundant topics per file).

    min_cluster_size scales with corpus size instead of being a fixed 2,
    since pooled per-query corpora are usually much larger than a single
    file's tweets.
    """
    if not BERTOPIC_AVAILABLE or len(texts) < 5:
        return []
    try:
        from umap import UMAP
        from hdbscan import HDBSCAN

        n = len(texts)
        umap_model = UMAP(
            n_neighbors  = min(n - 1, 15),
            n_components = min(n - 1, 5),
            min_dist     = 0.0,
            metric       = "cosine",
            random_state = 42
        )
        min_cluster_size = max(3, n // 50)
        hdbscan_model = HDBSCAN(
            min_cluster_size = min_cluster_size,
            min_samples      = 1,
            prediction_data  = True
        )
        model = BERTopic(
            umap_model     = umap_model,
            hdbscan_model  = hdbscan_model,
            verbose        = False,
            nr_topics      = "auto",
            min_topic_size = min_cluster_size
        )
        topics, _ = model.fit_transform(texts)
        info      = model.get_topic_info()
        result    = []
        for _, row in info[info["Topic"] != -1].head(top_n).iterrows():
            words = [w for w, _ in model.get_topic(row["Topic"])]
            result.append({
                "topic_id":  int(row["Topic"]),
                "words":     words[:8],
                "doc_count": int(row["Count"])
            })
        return result
    except Exception as e:
        log.warning(f"  BERTopic failed for query pool: {e}")
        return []


def generate_query_topics(conn):
    """Runs BERTopic once per query, pooling tweet text across all its fetch_runs."""
    if not BERTOPIC_AVAILABLE:
        return

    queries = conn.execute("SELECT id, query_text FROM queries").fetchall()
    log.info(f"\nRunning per-query BERTopic across {len(queries)} queries...")

    for q in queries:
        rows = conn.execute("""
            SELECT n.cleaned_text
            FROM tweet_nlp n
            JOIN tweets t     ON t.id = n.tweet_id
            JOIN fetch_runs r ON r.id = t.fetch_run_id
            WHERE r.query_id = ? AND n.cleaned_text IS NOT NULL AND n.cleaned_text != ''
        """, (q["id"],)).fetchall()
        texts = [row["cleaned_text"] for row in rows]

        if len(texts) < 10:   # Fix 16: BERTopic needs ≥10 docs
            log.info(f"  Skipping '{q['query_text']}' — only {len(texts)} docs (need >= 10)")
            continue

        log.info(f"  '{q['query_text']}': {len(texts)} pooled docs")
        topics = get_topics_bertopic(texts)
        n = insert_topics(conn, q["id"], topics)
        log.info(f"    ✓ {n} topics")


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

    total_files = len(processed_map)

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
            log.info(f"  ✓ {n_tweets} tweets")

            n_ht = insert_hashtags(conn, run_id, tweets)
            log.info(f"  ✓ {n_ht} hashtags")

            if nlp_data:
                nlp_tweets = nlp_data.get("tweets", [])
                n_nlp      = insert_nlp(conn, run_id, nlp_tweets)
                n_ent      = insert_entities(conn, run_id, nlp_tweets)
                n_kw       = insert_keywords(conn, run_id, nlp_tweets)
                n_events   = insert_events(conn, run_id, nlp_data.get("events", []))
                log.info(f"  ✓ {n_nlp} NLP | {n_ent} entities | {n_kw} keywords | "
                         f"{n_events} events")
            else:
                log.warning(f"  No NLP file found for {fname} — NLP tables skipped")

    # Fix 3: per-query BERTopic — run once per query after all files ingested
    with get_conn() as conn:
        generate_query_topics(conn)

    # BUG FIX: query actual DB row counts instead of summing insert-call
    # return values (which counted calls, not rows, inflating NLP rows: 1933 → 1121)
    with get_conn() as conn:
        actual_tweets   = conn.execute("SELECT COUNT(*) FROM tweets").fetchone()[0]
        actual_nlp      = conn.execute("SELECT COUNT(*) FROM tweet_nlp").fetchone()[0]
        actual_entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        actual_hashtags = conn.execute("SELECT COUNT(*) FROM hashtags").fetchone()[0]
        actual_keywords = conn.execute("SELECT COUNT(*) FROM keywords").fetchone()[0]

    log.info(f"\n{'='*55}")
    log.info(f"Ingestion complete — actual DB row counts:")
    log.info(f"  Tweets    : {actual_tweets:,}")
    log.info(f"  NLP rows  : {actual_nlp:,}")
    log.info(f"  Entities  : {actual_entities:,}")
    log.info(f"  Hashtags  : {actual_hashtags:,}")
    log.info(f"  Keywords  : {actual_keywords:,}")
    log.info(f"  Database  : {DB_PATH}")


if __name__ == "__main__":
    ingest_all()