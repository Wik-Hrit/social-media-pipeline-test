"""
visualise.py
Reads analysis_results.json and generates charts saved to data/charts/

Run: python visualise.py
"""

import json
import os
import logging
import matplotlib
matplotlib.use("Agg")   # non-interactive backend — works without a display
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import seaborn as sns
from wordcloud import WordCloud
from collections import defaultdict

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
log = logging.getLogger(__name__)

ANALYSIS_PATH = "data/analysis/analysis_results.json"
CHARTS_DIR    = "data/charts"
os.makedirs(CHARTS_DIR, exist_ok=True)

COLORS = {
    "positive": "#2ecc71",
    "neutral":  "#3498db",
    "negative": "#e74c3c",
}
PALETTE = ["#2E86AB", "#A23B72", "#F18F01", "#C73E1D", "#3B1F2B",
           "#44BBA4", "#E94F37", "#393E41", "#F5A623", "#7B2D8B"]


def load():
    if not os.path.exists(ANALYSIS_PATH):
        raise FileNotFoundError(f"{ANALYSIS_PATH} not found. Run analysis.py first.")
    with open(ANALYSIS_PATH, encoding="utf-8") as f:
        return json.load(f)


def short(q, max_len=20):
    """Shorten query label for axis."""
    return q if len(q) <= max_len else q[:max_len] + "…"


# ─────────────────────────────────────────────────────────────────────────────
# Chart 1 — Sentiment distribution (stacked bar)
# ─────────────────────────────────────────────────────────────────────────────

def chart_sentiment(sentiment: dict):
    queries  = list(sentiment.keys())
    labels   = [short(q) for q in queries]
    pos      = [sentiment[q]["positive"] for q in queries]
    neu      = [sentiment[q]["neutral"]  for q in queries]
    neg      = [sentiment[q]["negative"] for q in queries]

    x   = range(len(queries))
    fig, ax = plt.subplots(figsize=(14, 6))

    bars_neg = ax.bar(x, neg, label="Negative", color=COLORS["negative"])
    bars_neu = ax.bar(x, neu, bottom=neg, label="Neutral",  color=COLORS["neutral"])
    bars_pos = ax.bar(x, [p for p in pos],
                      bottom=[n + nu for n, nu in zip(neg, neu)],
                      label="Positive", color=COLORS["positive"])

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("Tweet Count")
    ax.set_title("Sentiment Distribution per Query (RoBERTa)", fontsize=14, fontweight="bold")
    ax.legend(loc="upper right")
    ax.yaxis.set_major_locator(mticker.MaxNLocator(integer=True))
    plt.tight_layout()

    path = os.path.join(CHARTS_DIR, "01_sentiment_distribution.png")
    plt.savefig(path, dpi=150)
    plt.close()
    log.info(f"  ✓ Saved → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Chart 2 — Word cloud (all keywords combined)
# ─────────────────────────────────────────────────────────────────────────────

def chart_wordcloud(keywords: dict):
    freq = defaultdict(int)
    for kws in keywords.values():
        for k in kws:
            freq[k["keyword"]] += k["count"]

    if not freq:
        log.warning("No keywords found — skipping word cloud")
        return

    wc = WordCloud(
        width=1400, height=700,
        background_color="white",
        colormap="tab20",
        max_words=150,
        collocations=False,
    ).generate_from_frequencies(freq)

    fig, ax = plt.subplots(figsize=(14, 7))
    ax.imshow(wc, interpolation="bilinear")
    ax.axis("off")
    ax.set_title("Top Keywords — All Queries Combined", fontsize=14, fontweight="bold")
    plt.tight_layout()

    path = os.path.join(CHARTS_DIR, "02_wordcloud_keywords.png")
    plt.savefig(path, dpi=150)
    plt.close()
    log.info(f"  ✓ Saved → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Chart 3 — Top hashtags per query (grouped bar)
# ─────────────────────────────────────────────────────────────────────────────

def chart_hashtags(hashtags: dict):
    fig, axes = plt.subplots(
        nrows=(len(hashtags) + 1) // 2, ncols=2,
        figsize=(16, max(6, 3 * ((len(hashtags) + 1) // 2)))
    )
    axes = axes.flatten()

    for idx, (query, tags) in enumerate(hashtags.items()):
        top   = tags[:8]
        names = [f"#{t['hashtag']}" for t in top]
        counts= [t["count"] for t in top]
        color = PALETTE[idx % len(PALETTE)]

        axes[idx].barh(names[::-1], counts[::-1], color=color)
        axes[idx].set_title(short(query, 28), fontsize=10, fontweight="bold")
        axes[idx].set_xlabel("Count", fontsize=8)
        axes[idx].tick_params(axis="y", labelsize=8)

    # hide unused subplots
    for idx in range(len(hashtags), len(axes)):
        axes[idx].set_visible(False)

    plt.suptitle("Top Hashtags per Query", fontsize=14, fontweight="bold", y=1.01)
    plt.tight_layout()

    path = os.path.join(CHARTS_DIR, "03_top_hashtags.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    log.info(f"  ✓ Saved → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Chart 4 — Engagement comparison (avg likes & retweets)
# ─────────────────────────────────────────────────────────────────────────────

def chart_engagement(engagement: dict):
    queries      = list(engagement.keys())
    labels       = [short(q) for q in queries]
    avg_likes    = [engagement[q]["avg_likes"]    for q in queries]
    avg_retweets = [engagement[q]["avg_retweets"] for q in queries]

    x   = range(len(queries))
    w   = 0.35
    fig, ax = plt.subplots(figsize=(14, 6))

    ax.bar([i - w/2 for i in x], avg_likes,    w, label="Avg Likes",    color="#F18F01")
    ax.bar([i + w/2 for i in x], avg_retweets, w, label="Avg Retweets", color="#2E86AB")

    ax.set_xticks(list(x))
    ax.set_xticklabels(labels, rotation=35, ha="right", fontsize=9)
    ax.set_ylabel("Average Count")
    ax.set_title("Engagement Comparison per Query", fontsize=14, fontweight="bold")
    ax.legend()
    plt.tight_layout()

    path = os.path.join(CHARTS_DIR, "04_engagement_comparison.png")
    plt.savefig(path, dpi=150)
    plt.close()
    log.info(f"  ✓ Saved → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Chart 5 — Source pie chart
# ─────────────────────────────────────────────────────────────────────────────

def chart_sources(sources: dict):
    labels = list(sources.keys())
    sizes  = list(sources.values())
    colors = ["#2E86AB", "#A23B72", "#F18F01"][:len(labels)]

    fig, ax = plt.subplots(figsize=(7, 7))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, colors=colors,
        autopct="%1.1f%%", startangle=140,
        textprops={"fontsize": 12}
    )
    for at in autotexts:
        at.set_fontsize(11)
        at.set_fontweight("bold")

    ax.set_title("Tweet Source Distribution\n(Twikit vs twitterapi.io)",
                 fontsize=13, fontweight="bold")
    plt.tight_layout()

    path = os.path.join(CHARTS_DIR, "05_source_distribution.png")
    plt.savefig(path, dpi=150)
    plt.close()
    log.info(f"  ✓ Saved → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Chart 6 — VADER vs RoBERTa agreement heatmap
# ─────────────────────────────────────────────────────────────────────────────

def chart_agreement(agreement: dict):
    import pandas as pd
    labels   = ["negative", "neutral", "positive"]
    matrix   = {l: {l2: 0 for l2 in labels} for l in labels}

    for row in agreement["breakdown"]:
        v = row.get("vader_label")
        r = row.get("roberta_label")
        if v in matrix and r in matrix[v]:
            matrix[v][r] = row["count"]

    df  = pd.DataFrame(matrix, index=labels, columns=labels)
    fig, ax = plt.subplots(figsize=(7, 6))
    sns.heatmap(df, annot=True, fmt="d", cmap="Blues",
                xticklabels=["VADER: " + l for l in labels],
                yticklabels=["RoBERTa: " + l for l in labels],
                ax=ax)
    ax.set_title(
        f"VADER vs RoBERTa Agreement\n(Agreement rate: {agreement['agreement_rate']}%)",
        fontsize=13, fontweight="bold"
    )
    plt.tight_layout()

    path = os.path.join(CHARTS_DIR, "06_vader_roberta_agreement.png")
    plt.savefig(path, dpi=150)
    plt.close()
    log.info(f"  ✓ Saved → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# Chart 7 — Tweet volume over time (line chart)
# ─────────────────────────────────────────────────────────────────────────────

def chart_volume(volume: dict):
    import pandas as pd
    from datetime import datetime

    def parse_date(d: str):
        """Handle both YYYY-MM-DD and 'Fri Jun 05' formats."""
        d = d.strip()
        for fmt in ("%Y-%m-%d", "%a %b %d", "%b %d"):
            try:
                dt = datetime.strptime(d, fmt)
                # if no year parsed, assume 2026
                if dt.year == 1900:
                    dt = dt.replace(year=2026)
                return dt
            except ValueError:
                continue
        return None

    fig, ax = plt.subplots(figsize=(16, 6))

    for idx, (query, points) in enumerate(volume.items()):
        if not points:
            continue
        parsed = [(parse_date(p["date"]), p["count"]) for p in points]
        parsed = [(d, c) for d, c in parsed if d is not None]
        if not parsed:
            continue
        parsed.sort(key=lambda x: x[0])
        dates  = [x[0] for x in parsed]
        counts = [x[1] for x in parsed]
        color  = PALETTE[idx % len(PALETTE)]
        ax.plot(dates, counts, marker="o", label=short(query, 22),
                color=color, linewidth=1.8, markersize=4)

    ax.set_xlabel("Date")
    ax.set_ylabel("Tweet Count")
    ax.set_title("Tweet Volume Over Time per Query", fontsize=14, fontweight="bold")
    ax.legend(fontsize=8, loc="upper left", bbox_to_anchor=(1, 1))

    import matplotlib.dates as mdates
    ax.xaxis.set_major_locator(mdates.AutoDateLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b %Y"))
    plt.xticks(rotation=45, ha="right", fontsize=8)
    plt.tight_layout()

    path = os.path.join(CHARTS_DIR, "07_tweet_volume_over_time.png")
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close()
    log.info(f"  ✓ Saved → {path}")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    log.info("Loading analysis results...")
    data = load()

    log.info("Generating charts...")
    chart_sentiment(data["sentiment"])
    chart_wordcloud(data["keywords"])
    chart_hashtags(data["hashtags"])
    chart_engagement(data["engagement"])
    chart_sources(data["sources"])
    chart_agreement(data["agreement"])
    chart_volume(data["volume"])

    log.info(f"All 7 charts saved to {CHARTS_DIR}/")
    print(f"\n✓ Charts saved to {CHARTS_DIR}/")
    print("  01_sentiment_distribution.png")
    print("  02_wordcloud_keywords.png")
    print("  03_top_hashtags.png")
    print("  04_engagement_comparison.png")
    print("  05_source_distribution.png")
    print("  06_vader_roberta_agreement.png")
    print("  07_tweet_volume_over_time.png")