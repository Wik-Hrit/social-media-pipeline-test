"""
dashboard.py
Interactive Streamlit dashboard for the Social Media NLP Pipeline.
Reads from pipeline.db directly — no need to run analysis.py first.

Usage: streamlit run dashboard.py
Install: pip install streamlit plotly pandas
"""

import os
import sys
import json
import sqlite3
from collections import defaultdict
from datetime import datetime

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from config import DB_PATH

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Social Media NLP Pipeline",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── DB helpers ────────────────────────────────────────────────────────────────
@st.cache_resource
def get_conn():
    if not os.path.exists(DB_PATH):
        st.error(f"{DB_PATH} not found. Run ingest.py first.")
        st.stop()
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@st.cache_data(ttl=300)
def load_queries():
    conn = get_conn()
    rows = conn.execute("SELECT query_text FROM queries ORDER BY query_text").fetchall()
    return [r["query_text"] for r in rows]


@st.cache_data(ttl=300)
def load_tweets(queries_filter):
    conn = get_conn()
    placeholders = ",".join("?" * len(queries_filter))
    df = pd.read_sql_query(f"""
        SELECT
            t.id, t.text, t.author, t.created_at, t.like_count,
            t.retweet_count, t.reply_count, t.view_count, t.lang,
            n.cleaned_text, n.final_label, n.final_confidence, n.final_source,
            n.vader_compound, n.roberta_label,
            n.eng_likes, n.eng_retweets, n.eng_views,
            q.query_text AS query
        FROM tweets t
        JOIN fetch_runs fr ON t.fetch_run_id = fr.id
        JOIN queries q     ON fr.query_id    = q.id
        LEFT JOIN tweet_nlp n ON n.tweet_id  = t.id
        WHERE q.query_text IN ({placeholders})
        ORDER BY t.created_at DESC
    """, conn, params=queries_filter)
    return df


@st.cache_data(ttl=300)
def load_entities(queries_filter):
    conn = get_conn()
    placeholders = ",".join("?" * len(queries_filter))
    df = pd.read_sql_query(f"""
        SELECT
            e.entity_text, e.entity_label, e.frequency,
            q.query_text AS query
        FROM entities e
        JOIN fetch_runs fr ON e.fetch_run_id = fr.id
        JOIN queries q     ON fr.query_id    = q.id
        WHERE q.query_text IN ({placeholders})
    """, conn, params=queries_filter)
    return df


@st.cache_data(ttl=300)
def load_hashtags(queries_filter):
    conn = get_conn()
    placeholders = ",".join("?" * len(queries_filter))
    df = pd.read_sql_query(f"""
        SELECT
            h.hashtag, COUNT(*) as count,
            q.query_text AS query
        FROM hashtags h
        JOIN fetch_runs fr ON h.fetch_run_id = fr.id
        JOIN queries q     ON fr.query_id    = q.id
        WHERE q.query_text IN ({placeholders})
        GROUP BY q.query_text, h.hashtag
        ORDER BY count DESC
    """, conn, params=queries_filter)
    return df


@st.cache_data(ttl=300)
def load_topics(queries_filter):
    conn = get_conn()
    placeholders = ",".join("?" * len(queries_filter))
    df = pd.read_sql_query(f"""
        SELECT
            tp.topic_id, tp.words, tp.doc_count,
            q.query_text AS query
        FROM topics tp
        JOIN queries q ON tp.query_id = q.id
        WHERE q.query_text IN ({placeholders})
        ORDER BY tp.doc_count DESC
    """, conn, params=queries_filter)
    return df


def mean_std(series):
    mu = series.mean()
    sd = series.std()
    return mu, sd


# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("🔍 Filters")

all_queries = load_queries()
if not all_queries:
    st.error("No queries found in DB. Run ingest.py first.")
    st.stop()

selected_queries = st.sidebar.multiselect(
    "Query topics",
    options=all_queries,
    default=all_queries,
)
if not selected_queries:
    st.warning("Select at least one query topic.")
    st.stop()

sentiment_filter = st.sidebar.multiselect(
    "Sentiment",
    options=["positive", "neutral", "negative"],
    default=["positive", "neutral", "negative"],
)

st.sidebar.markdown("---")
st.sidebar.caption(f"DB: `{DB_PATH}`")
st.sidebar.caption(f"Refreshed: {datetime.now().strftime('%H:%M:%S')}")
if st.sidebar.button("🔄 Refresh data"):
    st.cache_data.clear()
    st.rerun()

# ── Load data ─────────────────────────────────────────────────────────────────
df = load_tweets(selected_queries)
if df.empty:
    st.warning("No tweets found for selected queries.")
    st.stop()

if sentiment_filter:
    df = df[df["final_label"].isin(sentiment_filter)]

# ── Header ────────────────────────────────────────────────────────────────────
st.title("📊 Social Media NLP Pipeline Dashboard")
st.caption("IIT Guwahati — Multimodal Broadcast Analytics | twitter_acquisition branch")

# ── KPI row ───────────────────────────────────────────────────────────────────
k1, k2, k3, k4, k5 = st.columns(5)
k1.metric("Total Tweets",    f"{len(df):,}")
k2.metric("Queries",         len(selected_queries))
k3.metric("Positive",        f"{(df['final_label']=='positive').sum():,}")
k4.metric("Negative",        f"{(df['final_label']=='negative').sum():,}")
avg_likes = df['eng_likes'].mean() if "eng_likes" in df else None   # Fix 30
k5.metric("Avg Likes", f"{avg_likes:.1f}" if avg_likes is not None and pd.notna(avg_likes) else "—")

st.markdown("---")

# ── Row 1: Sentiment distribution + Pie ──────────────────────────────────────
col1, col2 = st.columns([2, 1])

with col1:
    st.subheader("Sentiment Distribution per Query")
    sent_df = (
        df.groupby(["query", "final_label"])
        .size()
        .reset_index(name="count")
    )
    if not sent_df.empty:
        fig = px.bar(
            sent_df, x="query", y="count", color="final_label",
            color_discrete_map={"positive": "#2ecc71", "neutral": "#3498db", "negative": "#e74c3c"},
            barmode="stack",
        )
        fig.update_layout(xaxis_tickangle=-30, legend_title="Sentiment",
                          xaxis_title="", yaxis_title="Tweets", height=380)
        st.plotly_chart(fig, use_container_width=True)

with col2:
    st.subheader("Overall Sentiment")
    overall = df["final_label"].value_counts().reset_index()
    overall.columns = ["sentiment", "count"]
    if not overall.empty:
        fig2 = px.pie(
            overall, values="count", names="sentiment",
            color="sentiment",
            color_discrete_map={"positive": "#2ecc71", "neutral": "#3498db", "negative": "#e74c3c"},
            hole=0.4,
        )
        fig2.update_layout(height=380)
        st.plotly_chart(fig2, use_container_width=True)

# ── Row 2: Engagement ─────────────────────────────────────────────────────────
st.subheader("Engagement by Query")
eng_df = df.groupby("query").agg(
    avg_likes=("eng_likes", "mean"),
    avg_retweets=("eng_retweets", "mean"),
    tweet_count=("id", "count"),
).reset_index()

ecol1, ecol2 = st.columns(2)
with ecol1:
    fig3 = px.bar(eng_df.sort_values("avg_likes", ascending=False),
                  x="query", y="avg_likes", color="query",
                  labels={"avg_likes": "Avg Likes", "query": ""},
                  title="Avg Likes per Query")
    fig3.update_layout(showlegend=False, xaxis_tickangle=-25, height=320)
    st.plotly_chart(fig3, use_container_width=True)

with ecol2:
    fig4 = px.bar(eng_df.sort_values("avg_retweets", ascending=False),
                  x="query", y="avg_retweets", color="query",
                  labels={"avg_retweets": "Avg Retweets", "query": ""},
                  title="Avg Retweets per Query")
    fig4.update_layout(showlegend=False, xaxis_tickangle=-25, height=320)
    st.plotly_chart(fig4, use_container_width=True)

# ── Row 3: Viral tweets ───────────────────────────────────────────────────────
st.subheader("🔥 Viral Tweets (mean + 2σ threshold per query)")
viral_rows = []
for query, group in df.groupby("query"):
    mu, sd = mean_std(group["eng_likes"].fillna(0))
    threshold = mu + 2 * sd
    viral = group[group["eng_likes"] > threshold].copy()
    if not viral.empty:
        viral["likes_threshold"] = round(threshold, 1)
        viral_rows.append(viral)

if viral_rows:
    viral_df = pd.concat(viral_rows).sort_values("eng_likes", ascending=False)
    st.dataframe(
        viral_df[["query", "author", "text", "eng_likes", "eng_retweets", "final_label", "likes_threshold"]]
        .rename(columns={"eng_likes": "likes", "eng_retweets": "retweets",
                         "final_label": "sentiment", "likes_threshold": "threshold"}),
        use_container_width=True, height=280,
    )
else:
    st.info("No viral tweets detected in current filter.")

# ── Row 4: Top entities + Hashtags ────────────────────────────────────────────
st.markdown("---")
ecol1, ecol2 = st.columns(2)

with ecol1:
    st.subheader("Top Named Entities")
    ent_df = load_entities(selected_queries)
    if not ent_df.empty:
        top_ents = (
            ent_df.groupby(["entity_text", "entity_label"])["frequency"]
            .sum()
            .reset_index()
            .sort_values("frequency", ascending=False)
            .head(20)
        )
        fig5 = px.bar(top_ents, x="frequency", y="entity_text",
                      color="entity_label", orientation="h",
                      labels={"entity_text": "", "frequency": "Count", "entity_label": "Type"})
        fig5.update_layout(height=480, yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig5, use_container_width=True)

with ecol2:
    st.subheader("Top Hashtags")
    ht_df = load_hashtags(selected_queries)
    if not ht_df.empty:
        top_ht = ht_df.groupby("hashtag")["count"].sum().reset_index().sort_values("count", ascending=False).head(20)
        fig6 = px.bar(top_ht, x="count", y="hashtag", orientation="h",
                      labels={"hashtag": "", "count": "Count"})
        fig6.update_layout(height=480, yaxis={"categoryorder": "total ascending"})
        st.plotly_chart(fig6, use_container_width=True)

# ── Row 5: BERTopic ───────────────────────────────────────────────────────────
st.subheader("BERTopic — Topics per Query")
topic_df = load_topics(selected_queries)
if topic_df.empty:
    st.info("No topics found. Run ingest.py with BERTopic enabled.")
else:
    for query in selected_queries:
        qt = topic_df[topic_df["query"] == query].head(5)
        if qt.empty:
            continue
        st.markdown(f"**{query}**")
        for _, row in qt.iterrows():
            words_raw = row["words"]                            # Fix 29
            if pd.isna(words_raw) if hasattr(pd, 'isna') else (words_raw != words_raw):
                words = []
            elif isinstance(words_raw, str):
                try:
                    words = json.loads(words_raw)
                except Exception:
                    words = []
            else:
                words = list(words_raw) if words_raw else []
            words_str = ", ".join(words[:8]) if words else "—"
            st.markdown(f"- Topic {row['topic_id']} ({row['doc_count']} docs): `{words_str}`")

# ── Row 6: Raw tweet browser ──────────────────────────────────────────────────
st.markdown("---")
st.subheader("Tweet Browser")
cols = ["query", "author", "text", "final_label", "final_confidence", "eng_likes", "eng_retweets", "created_at"]
available = [c for c in cols if c in df.columns]
st.dataframe(
    df[available].rename(columns={"final_label": "sentiment", "final_confidence": "confidence",
                                  "eng_likes": "likes", "eng_retweets": "retweets"}),
    use_container_width=True,
    height=380,
)

st.caption("Social Media NLP Pipeline · IIT Guwahati · twitter_acquisition")