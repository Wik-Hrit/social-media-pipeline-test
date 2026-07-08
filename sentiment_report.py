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

INPUT  = "data/analysis/analysis_results.json"
OUTPUT = "data/analysis/report.md"

if not os.path.exists(INPUT):
    print(f"ERROR: {INPUT} not found. Run analysis.py first.")
    sys.exit(1)

with open(INPUT, encoding="utf-8") as f:
    data = json.load(f)

sentiment  = data["sentiment"]
engagement = data["engagement"]
agreement  = data["agreement"]
entities   = data["entities"]
hashtags   = data["hashtags"]
keywords   = data["keywords"]

lines = []
w = lines.append

w("# Social Media NLP Pipeline — Insight Report")
w(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}  ")
w(f"**Queries analysed:** {len(sentiment)}  ")
w(f"**Total tweets:** {sum(s['total'] for s in sentiment.values()):,}\n")
w("---\n")

# ── 1. Sentiment highlights ───────────────────────────────────────────────────
w("## 1. Sentiment Distribution\n")

# most negative
neg_sorted = sorted(sentiment.items(), key=lambda x: x[1]["negative"] / max(x[1]["total"],1), reverse=True)
most_neg = neg_sorted[0]
neg_pct = most_neg[1]["negative"] / most_neg[1]["total"] * 100

# most positive
pos_sorted = sorted(sentiment.items(), key=lambda x: x[1]["positive"] / max(x[1]["total"],1), reverse=True)
most_pos = pos_sorted[0]
pos_pct = most_pos[1]["positive"] / most_pos[1]["total"] * 100

# most neutral
neu_sorted = sorted(sentiment.items(), key=lambda x: x[1]["neutral"] / max(x[1]["total"],1), reverse=True)
most_neu = neu_sorted[0]
neu_pct = most_neu[1]["neutral"] / most_neu[1]["total"] * 100

w(f"- **Most negative topic:** `{most_neg[0]}` — {neg_pct:.1f}% negative tweets")
w(f"- **Most positive topic:** `{most_pos[0]}` — {pos_pct:.1f}% positive tweets")
w(f"- **Most neutral topic:** `{most_neu[0]}` — {neu_pct:.1f}% neutral tweets\n")

w("| Query | Positive | Neutral | Negative | Total |")
w("|-------|----------|---------|----------|-------|")
for q, s in sorted(sentiment.items(), key=lambda x: x[1]["negative"], reverse=True):
    t = max(s["total"], 1)
    w(f"| {q} | {s['positive']/t*100:.0f}% | {s['neutral']/t*100:.0f}% | {s['negative']/t*100:.0f}% | {s['total']} |")
w("")

# ── 2. Model agreement ────────────────────────────────────────────────────────
w("## 2. VADER vs RoBERTa Agreement\n")
w(f"- **Agreement rate:** {agreement['agreement_rate']}%")
w(f"- **Total tweets compared:** {agreement['total_tweets']:,}")
w(f"- **Agreed:** {agreement['agreed']:,} | **Disagreed:** {agreement['disagreed']:,}")
w(f"\n> A {agreement['agreement_rate']}% agreement rate indicates {'strong' if agreement['agreement_rate'] > 60 else 'moderate'} "
  f"alignment between the rule-based (VADER) and transformer-based (RoBERTa) models. "
  f"Disagreements typically occur on sarcastic, mixed-sentiment, or domain-specific tweets.\n")

# ── 3. Engagement insights ────────────────────────────────────────────────────
w("## 3. Engagement Analysis\n")
top_eng = sorted(engagement.items(), key=lambda x: x[1]["avg_likes"], reverse=True)
w(f"- **Highest avg likes:** `{top_eng[0][0]}` — {top_eng[0][1]['avg_likes']:.1f} likes/tweet")
w(f"- **Highest avg retweets:** `{max(engagement.items(), key=lambda x: x[1]['avg_retweets'])[0]}`")
w(f"- **Highest avg views:** `{max(engagement.items(), key=lambda x: x[1]['avg_views'])[0]}`\n")

w("| Query | Tweets | Avg Likes | Avg Retweets | Avg Views |")
w("|-------|--------|-----------|--------------|-----------|")
for q, e in top_eng[:10]:
    w(f"| {q} | {e['tweet_count']} | {e['avg_likes']:.1f} | {e['avg_retweets']:.1f} | {e['avg_views']:.1f} |")
w("")

# ── 4. Top entities ───────────────────────────────────────────────────────────
w("## 4. Top Named Entities (All Queries)\n")
all_ents = {}
for q, elist in entities.items():
    for e in elist:
        key = (e["entity"], e["label"])
        all_ents[key] = all_ents.get(key, 0) + e["count"]

top_ents = sorted(all_ents.items(), key=lambda x: x[1], reverse=True)[:15]
w("| Entity | Type | Frequency |")
w("|--------|------|-----------|")
for (text, label), freq in top_ents:
    w(f"| {text} | {label} | {freq} |")
w("")

# ── 5. Top hashtags ───────────────────────────────────────────────────────────
w("## 5. Top Hashtags per Query\n")
for q, tags in list(hashtags.items())[:8]:
    top5 = ", ".join([f"`#{t['hashtag']}`" for t in tags[:5]])
    w(f"- **{q}:** {top5}")
w("")

# ── 6. Key findings ───────────────────────────────────────────────────────────
w("## 6. Key Findings\n")

crisis_topics = [q for q in sentiment if any(k in q.lower() for k in ["flood","conflict","attack","earthquake","heatwave"])]
crisis_neg = [(q, sentiment[q]["negative"]/max(sentiment[q]["total"],1)*100) for q in crisis_topics]
crisis_neg.sort(key=lambda x: x[1], reverse=True)

w("### Crisis vs Non-Crisis Sentiment")
if crisis_neg:
    avg_crisis_neg = sum(x[1] for x in crisis_neg) / len(crisis_neg)
    non_crisis = [q for q in sentiment if q not in crisis_topics]
    avg_non_crisis_neg = sum(sentiment[q]["negative"]/max(sentiment[q]["total"],1)*100 for q in non_crisis) / max(len(non_crisis),1)
    w(f"- Crisis-related topics averaged **{avg_crisis_neg:.1f}% negative** sentiment")
    w(f"- Non-crisis topics averaged **{avg_non_crisis_neg:.1f}% negative** sentiment")
    w(f"- Crisis topics with highest negativity:")
    for q, pct in crisis_neg[:3]:
        w(f"  - `{q}`: {pct:.1f}% negative")
w("")

w("### Engagement vs Sentiment Correlation")
high_eng = sorted(engagement.items(), key=lambda x: x[1]["avg_likes"], reverse=True)[:5]
w("Top 5 topics by engagement and their dominant sentiment:")
for q, e in high_eng:
    if q in sentiment:
        s = sentiment[q]
        dominant = max(["positive","neutral","negative"], key=lambda x: s[x])
        w(f"- `{q}`: {e['avg_likes']:.1f} avg likes — dominant sentiment: **{dominant}**")
w("")

w("---")
w(f"*Report generated by `sentiment_report.py` | Pipeline v2.0.0 | IIT Guwahati*")

os.makedirs(os.path.dirname(OUTPUT), exist_ok=True)
with open(OUTPUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"✓ Report saved → {OUTPUT}")