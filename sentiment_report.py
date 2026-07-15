"""
sentiment_report.py
Auto-generates a human-readable markdown insight report from analysis_results.json.
Output: data/analysis/report.md

Run: python sentiment_report.py
"""

import json
import os
import sys
from datetime import datetime
from config import ANALYSIS_DIR

INPUT  = os.path.join(ANALYSIS_DIR, "analysis_results.json")
OUTPUT = os.path.join(ANALYSIS_DIR, "report.md")


def main():
    if not os.path.exists(INPUT):
        print(f"ERROR: {INPUT} not found. Run analysis.py first.")
        sys.exit(1)

    with open(INPUT, encoding="utf-8") as f:
        data = json.load(f)

    sentiment  = data.get("sentiment",  {})
    engagement = data.get("engagement", {})
    agreement  = data.get("agreement",  {})
    entities   = data.get("entities",   {})
    hashtags   = data.get("hashtags",   {})
    keywords   = data.get("keywords",   {})

    lines = []

    def w(line=""):
        lines.append(line)

    w(f"# Social Media NLP Pipeline — Insight Report")
    w(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
    w(f"**Source:** `{INPUT}`\n")
    w("---\n")

    # ── 1. Sentiment summary ──────────────────────────────────────────────────
    w("## 1. Sentiment Overview\n")
    overall = sentiment.get("overall", {})
    total   = overall.get("total", 0)
    pos     = overall.get("positive", 0)
    neu     = overall.get("neutral", 0)
    neg     = overall.get("negative", 0)

    w(f"- **Total tweets analysed:** {total:,}")
    w(f"- **Positive:** {pos} ({pos/total*100:.1f}%)" if total else "- **Positive:** 0")
    w(f"- **Neutral:** {neu} ({neu/total*100:.1f}%)"  if total else "- **Neutral:** 0")
    w(f"- **Negative:** {neg} ({neg/total*100:.1f}%)" if total else "- **Negative:** 0")
    w("")

    by_query = sentiment.get("by_query", {})
    if by_query:
        most_pos = max(by_query.items(), key=lambda x: x[1].get("positive_pct", 0), default=(None, {}))[0]
        most_neg = max(by_query.items(), key=lambda x: x[1].get("negative_pct", 0), default=(None, {}))[0]
        w(f"- **Most positive query:** `{most_pos}`")
        w(f"- **Most negative query:** `{most_neg}`\n")

    # ── 2. VADER vs RoBERTa ───────────────────────────────────────────────────
    w("## 2. VADER vs RoBERTa Agreement\n")
    w(f"- **Agreement rate:** {agreement.get('agreement_rate', 0)}%")
    w(f"- **Agreed:** {agreement.get('agreed', 0):,} tweets")
    w(f"- **Disagreed:** {agreement.get('disagreed', 0):,} tweets\n")

    # ── 3. Engagement insights ────────────────────────────────────────────────
    w("## 3. Engagement Analysis\n")
    if engagement:
        top_eng = sorted(engagement.items(), key=lambda x: x[1].get("avg_likes") or 0, reverse=True)

        w(f"- **Highest avg likes:** `{top_eng[0][0]}` — {top_eng[0][1].get('avg_likes') or 0:.1f} likes/tweet")

        top_rt  = max(engagement.items(), key=lambda x: x[1].get("avg_retweets") or 0, default=(None, {}))[0]
        top_vw  = max(engagement.items(), key=lambda x: x[1].get("avg_views") or 0, default=(None, {}))[0]   # Fix 8
        w(f"- **Highest avg retweets:** `{top_rt}`")
        w(f"- **Highest avg views:** `{top_vw}`\n")

        w("| Query | Tweets | Avg Likes | Avg Retweets | Avg Views |")
        w("|-------|--------|-----------|--------------|-----------|")
        for q, e in top_eng[:10]:
            avg_views = e.get("avg_views") or 0   # Fix 8: None → 0
            w(f"| {q} | {e.get('tweet_count',0)} | {e.get('avg_likes') or 0:.1f} | "
              f"{e.get('avg_retweets') or 0:.1f} | {avg_views:.1f} |")
        w("")

    # ── 4. Top entities ───────────────────────────────────────────────────────
    w("## 4. Top Named Entities (All Queries)\n")
    all_ents = {}
    for q, elist in entities.items():
        for e in elist:
            key = (e["entity"], e["label"])
            all_ents[key] = all_ents.get(key, 0) + e["count"]

    top_ents = sorted(all_ents.items(), key=lambda x: x[1], reverse=True)[:15]
    w("| Entity | Type | Frequency |")
    w("|--------|------|-----------|")
    for (ent, label), cnt in top_ents:
        w(f"| {ent} | {label} | {cnt} |")
    w("")

    # ── 5. Top hashtags ───────────────────────────────────────────────────────
    w("## 5. Top Hashtags\n")
    all_tags = {}
    for q, tags in hashtags.items():
        for t in tags:
            tag = t["hashtag"]
            all_tags[tag] = all_tags.get(tag, 0) + t["count"]
    top_tags = sorted(all_tags.items(), key=lambda x: x[1], reverse=True)[:15]
    w("| Hashtag | Count |")
    w("|---------|-------|")
    for tag, cnt in top_tags:
        w(f"| #{tag} | {cnt} |")
    w("")

    # ── 6. Top keywords ───────────────────────────────────────────────────────
    w("## 6. Top TF-IDF Keywords\n")
    all_kw = {}
    for q, kws in keywords.items():
        for k in kws:
            all_kw[k["keyword"]] = all_kw.get(k["keyword"], 0) + k["count"]
    top_kw = sorted(all_kw.items(), key=lambda x: x[1], reverse=True)[:20]
    w(", ".join([f"`{k}`" for k, _ in top_kw]))
    w("")

    w("---")
    w(f"*Report generated by `sentiment_report.py` | Pipeline v2.0.0 | IIT Guwahati*")

    os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
    with open(OUTPUT, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"✓ Report saved → {OUTPUT}")


if __name__ == "__main__":   # Fix 9
    main()