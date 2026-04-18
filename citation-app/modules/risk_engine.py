"""
Contamination Risk Engine.

Risk Formula (updated):
    depth_weight = 1 / hop_level   →  {hop1: 1.0, hop2: 0.5, hop3: 0.33}
    risk_score   = depth_weight × sentiment_weight × log(1 + citation_count)
    if retracted → × 2.0

Sentiment weights:
    Endorsing  = 1.5  (treats invalid science as valid → high contamination)
    Neutral    = 1.0  (cites as context → moderate risk)
    Critiquing = 0.0  (opposes / refutes → SAFE, zero contamination)

Contamination Score (headline KPI, 0–100):
    (HIGH×1.0 + MEDIUM×0.6 + LOW×0.3) / total_papers × 100
"""

import math
import logging

from .sentiment_analyzer import classify_sentiment, get_sentiment_weight

logger = logging.getLogger(__name__)

RETRACTED_MULTIPLIER = 2.0

HIGH_RISK_KEYWORDS = [
    "systematic review", "meta-analysis", "meta analysis",
    "pooled analysis", "umbrella review", "evidence synthesis",
]


def _depth_weight(depth: int) -> float:
    """1/depth for hop >= 1, 0 for root (depth=0)."""
    if depth <= 0:
        return 0.0
    return 1.0 / depth


def compute_risk_score(
    depth: int,
    citation_count: int | None,
    abstract: str | None = None,
    title: str | None = None,
    is_retracted: bool = False,
) -> tuple[float, str]:
    """
    Returns (risk_score, sentiment_label).
    Critiquing papers score 0.0 — they oppose the root paper's claims.
    """
    dw        = _depth_weight(depth)
    cc        = citation_count if citation_count is not None else 0
    influence = math.log1p(cc)

    sentiment        = classify_sentiment(abstract, title)
    sentiment_weight = get_sentiment_weight(sentiment)   # 0.0 for Critiquing

    score = dw * sentiment_weight * influence

    if is_retracted:
        score *= RETRACTED_MULTIPLIER

    return round(score, 4), sentiment


def is_high_risk_by_keywords(title: str | None, abstract: str | None) -> bool:
    """Systematic reviews / meta-analyses amplify contamination → flag them."""
    text = ""
    if title:    text += title.lower() + " "
    if abstract: text += abstract.lower()
    return any(kw in text for kw in HIGH_RISK_KEYWORDS)


def classify_risk_level(
    risk_score: float,
    is_high_risk_keyword: bool,
    sentiment: str = "Neutral",
) -> str:
    if sentiment == "Critiquing":
        return "SAFE"
    if is_high_risk_keyword and sentiment == "Endorsing":
        return "HIGH"
    if risk_score >= 3.0 or (is_high_risk_keyword and risk_score >= 1.0):
        return "HIGH"
    if risk_score >= 1.5:
        return "MEDIUM"
    return "LOW"


def rank_papers(papers: list[dict]) -> list[dict]:
    """SAFE papers sorted to bottom; rest sorted by risk_score desc."""
    def key(p):
        is_safe = 1 if p.get("sentiment") == "Critiquing" else 0
        return (is_safe, -(p.get("risk_score") or 0.0), -(p.get("citation_count") or 0))
    return sorted(papers, key=key)


def compute_contamination_score(papers: list[dict]) -> float:
    """
    Headline KPI (0–100):
        (HIGH×1.0 + MEDIUM×0.6 + LOW×0.3) / total × 100
    Excludes root paper (depth=0) and SAFE papers.
    """
    candidates = [p for p in papers if p.get("depth_level", 0) > 0]
    total = len(candidates)
    if total == 0:
        return 0.0
    high   = sum(1 for p in candidates if p.get("risk_level") == "HIGH")
    medium = sum(1 for p in candidates if p.get("risk_level") == "MEDIUM")
    low    = sum(1 for p in candidates if p.get("risk_level") == "LOW")
    score  = (high * 1.0 + medium * 0.6 + low * 0.3) / total * 100
    return round(score, 1)


def compute_analytics(papers: list[dict], retraction_year: int | None = None) -> dict:
    if not papers:
        return {
            "total": 0, "contaminated": 0, "safe": 0,
            "high_risk": 0, "medium_risk": 0, "low_risk": 0,
            "retracted_in_network": 0, "max_depth": 0,
            "contamination_score": 0.0,
            "by_level": {1: 0, 2: 0, 3: 0},
            "by_sentiment": {"Endorsing": 0, "Neutral": 0, "Critiquing": 0},
            "before_retraction": 0, "after_retraction": 0,
            "before_pct": 0.0, "after_pct": 0.0,
            "top10": [], "insights": [],
        }

    total     = len(papers)
    high      = [p for p in papers if p.get("risk_level") == "HIGH"]
    medium    = [p for p in papers if p.get("risk_level") == "MEDIUM"]
    low       = [p for p in papers if p.get("risk_level") == "LOW"]
    safe      = [p for p in papers if p.get("risk_level") == "SAFE"]
    retracted = [p for p in papers if p.get("is_retracted")]

    by_level    = {1: 0, 2: 0, 3: 0}
    by_sentiment = {"Endorsing": 0, "Neutral": 0, "Critiquing": 0}
    max_depth   = 0

    for p in papers:
        d = p.get("depth_level", 0)
        if d in by_level:
            by_level[d] += 1
        if d > max_depth:
            max_depth = d
        s = p.get("sentiment", "Neutral")
        if s in by_sentiment:
            by_sentiment[s] += 1

    # Time-based analysis
    papers_with_year = [p for p in papers if p.get("year") and p.get("depth_level", 0) > 0]
    before = after = 0
    if retraction_year and papers_with_year:
        before = sum(1 for p in papers_with_year if p["year"] < retraction_year)
        after  = sum(1 for p in papers_with_year if p["year"] >= retraction_year)
        dated_total = before + after
        before_pct = round(before / dated_total * 100, 1) if dated_total else 0
        after_pct  = round(after  / dated_total * 100, 1) if dated_total else 0
    else:
        before_pct = after_pct = 0.0

    contamination_score = compute_contamination_score(papers)

    # Top 10: highest-risk non-safe papers (exclude root depth=0)
    risky = [p for p in papers if p.get("risk_level") not in ("SAFE",) and p.get("depth_level", 0) > 0]
    top10 = sorted(risky, key=lambda p: -(p.get("risk_score") or 0))[:10]

    # Auto-generated insights
    insights = _generate_insights(
        papers, by_level, by_sentiment,
        len(high), len(medium), len(safe),
        retraction_year, before, after, before_pct, after_pct,
        contamination_score,
    )

    return {
        "total":                total,
        "contaminated":         len(high) + len(medium),
        "safe":                 len(safe),
        "high_risk":            len(high),
        "medium_risk":          len(medium),
        "low_risk":             len(low),
        "retracted_in_network": len(retracted),
        "max_depth":            max_depth,
        "contamination_score":  contamination_score,
        "by_level":             by_level,
        "by_sentiment":         by_sentiment,
        "before_retraction":    before,
        "after_retraction":     after,
        "before_pct":           before_pct,
        "after_pct":            after_pct,
        "top10":                top10,
        "insights":             insights,
    }


def _generate_insights(
    papers, by_level, by_sentiment,
    n_high, n_medium, n_safe,
    retraction_year, before, after, before_pct, after_pct,
    contamination_score,
) -> list[dict]:
    """
    Auto-generate 3–5 plain-language insights from the data.
    Each insight: {icon, text, severity}  severity: info|warning|danger|good
    """
    insights = []
    total_network = [p for p in papers if p.get("depth_level", 0) > 0]
    total = len(total_network)

    # 1. Dominant hop level
    if by_level:
        dominant_hop = max(by_level, key=lambda k: by_level[k])
        dominant_count = by_level[dominant_hop]
        if dominant_count > 0:
            insights.append({
                "icon": "🔗",
                "text": f"Most contamination occurs at Hop {dominant_hop} — "
                        f"{dominant_count} papers directly cite the root paper.",
                "severity": "warning" if dominant_hop == 1 else "info",
            })

    # 2. Endorsing vs Critiquing
    n_endorsing  = by_sentiment.get("Endorsing", 0)
    n_critiquing = by_sentiment.get("Critiquing", 0)
    if n_endorsing > 0 and total > 0:
        endorse_pct = round(n_endorsing / total * 100, 1)
        insights.append({
            "icon": "⚠️",
            "text": f"{endorse_pct}% of citing papers ({n_endorsing}) endorse the root paper's findings — "
                    "these are the primary contamination vectors.",
            "severity": "danger" if endorse_pct > 40 else "warning",
        })

    # 3. Safe papers as containment
    if n_safe > 0 and total > 0:
        safe_pct = round(n_safe / total * 100, 1)
        insights.append({
            "icon": "🛡️",
            "text": f"{n_safe} papers ({safe_pct}%) actively critique or refute the root paper — "
                    "these act as scientific containment, correcting the record.",
            "severity": "good",
        })

    # 4. Time-based insight
    if retraction_year and (before + after) > 0:
        if after > before:
            insights.append({
                "icon": "📅",
                "text": f"{after_pct}% of citations ({after} papers) occurred AFTER the retraction year "
                        f"({retraction_year}) — meaning the contaminated science continued spreading post-retraction.",
                "severity": "danger",
            })
        else:
            insights.append({
                "icon": "📅",
                "text": f"{before_pct}% of citations ({before} papers) occurred BEFORE the retraction "
                        f"({retraction_year}), suggesting early spread before the retraction was known.",
                "severity": "info",
            })

    # 5. Overall severity
    if contamination_score >= 70:
        insights.append({
            "icon": "🚨",
            "text": f"CRITICAL: Contamination score of {contamination_score}/100 indicates severe propagation. "
                    "This paper's retraction has had widespread downstream impact.",
            "severity": "danger",
        })
    elif contamination_score >= 40:
        insights.append({
            "icon": "⚡",
            "text": f"Contamination score of {contamination_score}/100 indicates moderate spread. "
                    "Several downstream papers may carry invalid assumptions.",
            "severity": "warning",
        })
    else:
        insights.append({
            "icon": "✅",
            "text": f"Contamination score of {contamination_score}/100 indicates limited spread. "
                    "Most citing papers maintain scientific independence.",
            "severity": "info",
        })

    return insights
