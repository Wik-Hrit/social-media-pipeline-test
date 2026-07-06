"""
db_manager.py
SQLite database layer — Social Media Acquisition Pipeline
Multimodal Broadcast Analytics System, IIT Guwahati

9 Tables:
    1. queries       — unique query strings
    2. fetch_runs    — one per processed JSON file
    3. tweets        — base tweet fields  (data/processed/)
    4. tweet_nlp     — NLP enrichment     (data/nlp/)
    5. entities      — named entities, normalized
    6. hashtags      — one row per hashtag per tweet (normalized)
    7. keywords      — one row per TF-IDF keyword per tweet (normalized)
    8. topics        — BERTopic output per run
    9. events        — keyword frequency events per run
"""

import sqlite3
import json
import logging
from contextlib import contextmanager
from datetime import datetime

log = logging.getLogger(__name__)
DB_PATH = "pipeline.db"

# Semantically meaningful NER labels — filters out CARDINAL, ORDINAL, QUANTITY etc.
SEMANTIC_ENTITY_LABELS = {
    "PERSON", "ORG", "GPE", "LOC", "EVENT",
    "PRODUCT", "WORK_OF_ART", "LAW", "LANGUAGE", "NORP"
}


@contextmanager
def get_conn(db_path: str = DB_PATH):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str = DB_PATH):
    with get_conn(db_path) as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS queries (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                query_text  TEXT    NOT NULL UNIQUE,
                created_at  TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS fetch_runs (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                query_id         INTEGER NOT NULL REFERENCES queries(id),
                fetched_at       TEXT,
                api_source       TEXT,
                tweet_count      INTEGER,
                preprocessed_at  TEXT,
                original_count   INTEGER,
                after_filter     INTEGER,
                after_dedup      INTEGER,
                final_count      INTEGER,
                device           TEXT,
                processed_file   TEXT,
                nlp_file         TEXT
            );
            CREATE TABLE IF NOT EXISTS tweets (
                id               TEXT    PRIMARY KEY,
                fetch_run_id     INTEGER NOT NULL REFERENCES fetch_runs(id),
                text             TEXT,
                created_at       TEXT,
                author           TEXT,
                author_followers INTEGER,
                retweet_count    INTEGER DEFAULT 0,
                like_count       INTEGER DEFAULT 0,
                reply_count      INTEGER DEFAULT 0,
                view_count       INTEGER,
                lang             TEXT,
                url              TEXT,
                is_reply         INTEGER DEFAULT 0,
                is_retweet       INTEGER DEFAULT 0,
                source           TEXT
            );
            CREATE TABLE IF NOT EXISTS tweet_nlp (
                tweet_id          TEXT    PRIMARY KEY REFERENCES tweets(id),
                fetch_run_id      INTEGER NOT NULL REFERENCES fetch_runs(id),
                cleaned_text      TEXT,
                tokens            TEXT    DEFAULT '[]',
                lemmatized_tokens TEXT    DEFAULT '[]',
                mentions          TEXT    DEFAULT '[]',
                emojis            TEXT    DEFAULT '[]',
                urls              TEXT    DEFAULT '[]',
                vader_compound    REAL,
                vader_pos         REAL,
                vader_neu         REAL,
                vader_neg         REAL,
                vader_label       TEXT,
                roberta_label     TEXT,
                roberta_neg       REAL,
                roberta_neu       REAL,
                roberta_pos       REAL,
                final_label       TEXT,
                eng_likes         INTEGER DEFAULT 0,
                eng_retweets      INTEGER DEFAULT 0,
                eng_replies       INTEGER DEFAULT 0,
                eng_views         INTEGER,
                eng_bookmarks     INTEGER
            );
            CREATE TABLE IF NOT EXISTS entities (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tweet_id     TEXT    NOT NULL REFERENCES tweets(id),
                fetch_run_id INTEGER NOT NULL REFERENCES fetch_runs(id),
                entity_text  TEXT    NOT NULL,
                entity_label TEXT    NOT NULL,
                frequency    INTEGER DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS hashtags (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tweet_id     TEXT    NOT NULL REFERENCES tweets(id),
                fetch_run_id INTEGER NOT NULL REFERENCES fetch_runs(id),
                hashtag      TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS keywords (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                tweet_id     TEXT    NOT NULL REFERENCES tweets(id),
                fetch_run_id INTEGER NOT NULL REFERENCES fetch_runs(id),
                keyword      TEXT    NOT NULL
            );
            CREATE TABLE IF NOT EXISTS topics (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                fetch_run_id INTEGER NOT NULL REFERENCES fetch_runs(id),
                topic_id     INTEGER NOT NULL,
                words        TEXT    DEFAULT '[]'
            );
            CREATE TABLE IF NOT EXISTS events (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                fetch_run_id INTEGER NOT NULL REFERENCES fetch_runs(id),
                keyword      TEXT    NOT NULL,
                count        INTEGER NOT NULL,
                freq_ratio   REAL
            );
            CREATE INDEX IF NOT EXISTS idx_tweets_run     ON tweets(fetch_run_id);
            CREATE INDEX IF NOT EXISTS idx_tweets_author  ON tweets(author);
            CREATE INDEX IF NOT EXISTS idx_tweets_created ON tweets(created_at);
            CREATE INDEX IF NOT EXISTS idx_nlp_label      ON tweet_nlp(final_label);
            CREATE INDEX IF NOT EXISTS idx_nlp_vader      ON tweet_nlp(vader_compound);
            CREATE INDEX IF NOT EXISTS idx_entities_text  ON entities(entity_text);
            CREATE INDEX IF NOT EXISTS idx_entities_label ON entities(entity_label);
            CREATE INDEX IF NOT EXISTS idx_hashtags_tag   ON hashtags(hashtag);
            CREATE INDEX IF NOT EXISTS idx_keywords_kw    ON keywords(keyword);
            CREATE INDEX IF NOT EXISTS idx_runs_query     ON fetch_runs(query_id);
        """)
    log.info(f"Database initialized → {db_path} (9 tables)")


def _j(value) -> str:
    if value is None: return "[]"
    return json.dumps(value, ensure_ascii=False)


def upsert_query(conn, query_text: str) -> int:
    conn.execute(
        "INSERT OR IGNORE INTO queries (query_text, created_at) VALUES (?, ?)",
        (query_text, datetime.now().isoformat())
    )
    return conn.execute("SELECT id FROM queries WHERE query_text = ?", (query_text,)).fetchone()["id"]


def insert_fetch_run(conn, query_id: int, metadata: dict,
                     processed_file=None, nlp_file=None) -> int:
    cur = conn.execute("""
        INSERT INTO fetch_runs
            (query_id, fetched_at, api_source, tweet_count,
             preprocessed_at, original_count, after_filter,
             after_dedup, final_count, device, processed_file, nlp_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (query_id, metadata.get("fetchedAt"), metadata.get("apiSource"),
          metadata.get("tweetCount"), metadata.get("preprocessedAt"),
          metadata.get("originalCount"), metadata.get("afterFilter"),
          metadata.get("afterDedup"), metadata.get("finalCount"),
          metadata.get("device"), processed_file, nlp_file))
    return cur.lastrowid


def insert_tweets(conn, fetch_run_id: int, tweets: list, default_source=None) -> int:
    inserted = 0
    for t in tweets:
        source = t.get("source") or default_source
        try:
            cur = conn.execute("""
                INSERT OR IGNORE INTO tweets
                    (id, fetch_run_id, text, created_at, author,
                     author_followers, retweet_count, like_count,
                     reply_count, view_count, lang, url,
                     is_reply, is_retweet, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (str(t.get("id")), fetch_run_id, t.get("text"), t.get("createdAt"),
                  t.get("author"), t.get("authorFollowers"),
                  t.get("retweetCount", 0), t.get("likeCount", 0),
                  t.get("replyCount", 0), t.get("viewCount"),
                  t.get("lang"), t.get("url"),
                  int(bool(t.get("isReply", False))),
                  int(bool(t.get("isRetweet", False))), source))
            # D2: use rowcount > 0 — OR IGNORE skipped rows don't count
            if cur.rowcount > 0:
                inserted += 1
        except Exception as e:
            log.warning(f"Tweet insert failed {t.get('id')}: {e}")
    return inserted


def insert_nlp(conn, fetch_run_id: int, tweets: list) -> int:
    inserted = 0
    for t in tweets:
        tweet_id   = str(t.get("id"))
        sentiment  = t.get("sentiment", {})
        vader      = sentiment.get("vader", {})
        roberta    = sentiment.get("roberta", {})
        rob_scores = roberta.get("scores", {})
        eng        = t.get("engagement", {})
        try:
            conn.execute("""
                INSERT OR REPLACE INTO tweet_nlp
                    (tweet_id, fetch_run_id, cleaned_text,
                     tokens, lemmatized_tokens, mentions, emojis, urls,
                     vader_compound, vader_pos, vader_neu, vader_neg, vader_label,
                     roberta_label, roberta_neg, roberta_neu, roberta_pos, final_label,
                     eng_likes, eng_retweets, eng_replies, eng_views, eng_bookmarks)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (tweet_id, fetch_run_id, t.get("cleaned_text"),
                  _j(t.get("tokens", [])), _j(t.get("lemmatized_tokens", [])),
                  _j(t.get("mentions", [])), _j(t.get("emojis", [])), _j(t.get("urls", [])),
                  vader.get("compound"), vader.get("pos"), vader.get("neu"), vader.get("neg"), vader.get("label"),
                  roberta.get("label"), rob_scores.get("negative"), rob_scores.get("neutral"), rob_scores.get("positive"),
                  sentiment.get("final_label"),
                  eng.get("likes", 0), eng.get("retweets", 0), eng.get("replies", 0),
                  eng.get("views"), eng.get("bookmarks")))
            inserted += 1
        except Exception as e:
            log.warning(f"NLP insert failed {tweet_id}: {e}")
    return inserted


def insert_entities(conn, fetch_run_id: int, tweets: list) -> int:
    """D1: Use seen set — prevents duplicate entity rows."""
    inserted = 0
    for t in tweets:
        tweet_id    = str(t.get("id"))
        entity_freq = t.get("entity_freq", {})
        seen        = set()   # D1: dedup per tweet
        for ent in t.get("entities", []):
            key = (tweet_id, ent.get("text",""), ent.get("label",""))
            if key in seen:
                continue
            if ent.get("label", "") not in SEMANTIC_ENTITY_LABELS:
                continue
            seen.add(key)
            try:
                conn.execute("""
                    INSERT INTO entities
                        (tweet_id, fetch_run_id, entity_text, entity_label, frequency)
                    VALUES (?, ?, ?, ?, ?)
                """, (tweet_id, fetch_run_id,
                      ent.get("text",""), ent.get("label",""),
                      entity_freq.get(ent.get("text",""), 1)))
                inserted += 1
            except Exception as e:
                log.warning(f"Entity insert failed: {e}")
    return inserted


def insert_hashtags(conn, fetch_run_id: int, tweets: list) -> int:
    inserted = 0
    for t in tweets:
        tweet_id = str(t.get("id"))
        seen = set()   # D3: dedup per tweet
        for tag in t.get("hashtags", []):
            if tag and tag.lower() not in seen:
                seen.add(tag.lower())
                try:
                    conn.execute(
                        "INSERT INTO hashtags (tweet_id, fetch_run_id, hashtag) VALUES (?, ?, ?)",
                        (tweet_id, fetch_run_id, tag.lower()))
                    inserted += 1
                except Exception as e:
                    log.warning(f"Hashtag insert failed: {e}")
    return inserted


def insert_keywords(conn, fetch_run_id: int, tweets: list) -> int:
    inserted = 0
    for t in tweets:
        tweet_id = str(t.get("id"))
        seen = set()   # D4: dedup per tweet
        for kw in t.get("keywords", []):
            if kw and kw not in seen:
                seen.add(kw)
                try:
                    conn.execute(
                        "INSERT INTO keywords (tweet_id, fetch_run_id, keyword) VALUES (?, ?, ?)",
                        (tweet_id, fetch_run_id, kw))
                    inserted += 1
                except Exception as e:
                    log.warning(f"Keyword insert failed: {e}")
    return inserted


def insert_topics(conn, fetch_run_id: int, topics: list) -> int:
    inserted = 0
    for topic in topics:
        conn.execute(
            "INSERT INTO topics (fetch_run_id, topic_id, words) VALUES (?, ?, ?)",
            (fetch_run_id, topic.get("topic_id"), _j(topic.get("words", []))))
        inserted += 1
    return inserted


def insert_events(conn, fetch_run_id: int, events: list) -> int:
    inserted = 0
    for event in events:
        conn.execute(
            "INSERT INTO events (fetch_run_id, keyword, count, freq_ratio) VALUES (?, ?, ?, ?)",
            (fetch_run_id, event.get("keyword"), event.get("count"), event.get("freq_ratio")))
        inserted += 1
    return inserted