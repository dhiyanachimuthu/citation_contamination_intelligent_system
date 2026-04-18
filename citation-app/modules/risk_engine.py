"""
Contamination Risk Engine.

Full risk formula:
    risk_score = depth_weight × sentiment_weight × log(1 + citation_count)
    if retracted → × 2.0

Sentiment weights:
    Endorsing  = 1.5  (treats invalid science as valid → high contamination)
    Neutral    = 1.0  (cites as context → moderate risk)
    Critiquing = 0.0  (opposes / refutes → SAFE, not contaminated)

Risk levels:
    SAFE     — Critiquing papers (they correct, not spread, contamination)
    LOW      — score < 1.5 and not a systematic review
    MEDIUM   — score ≥ 1.5
    HIGH     — score ≥ 3.0 OR is a systematic review / meta-analysis
    RETRACTED — the paper itself is retracted
"""

import math
import logging

from .sentiment_analyzer import classify_sentiment, get_sentiment_weight

logger = logging.getLogger(__name__)

DEPTH_WEIGHTS       = {0: 0.0, 1: 1.0, 2: 0.5, 3: 0.2}
RETRACTED_MULTIPLIER = 2.0

HIGH_RISK_KEYWORDS = [
    "systematic review", "meta-analysis", "meta analysis",
    "pooled analysis", "umbrella review", "evidence synthesis",
]


def compute_risk_score(
    depth: int,
    citation_count: int | None,
    abstract: str | None = None,
    title: str | None = None,
    is_retracted: bool = False,
) -> tuple[float, str]:
    """
    Compute contamination risk score.

    Returns (risk_score, sentiment_label).

    Critiquing papers score 0.0 because they actively oppose the retracted
    paper's claims — they reduce contamination, not spread it.
    """
    depth_weight     = DEPTH_WEIGHTS.get(depth, 0.1)
    cc               = citation_count if citation_count is not None else 0
    influence        = math.log1p(cc)

    sentiment        = classify_sentiment(abstract, title)
    sentiment_weight = get_sentiment_weight(sentiment)  # 0.0 for Critiquing

    score = depth_weight * sentiment_weight * influence

    if is_retracted:
        score *= RETRACTED_MULTIPLIER

    return round(score, 4), sentiment


def is_high_risk_by_keywords(title: str | None, abstract: str | None) -> bool:
    """
    True if paper is a systematic review / meta-analysis —
    these amplify contamination because they aggregate evidence.
    """
    text = ""
    if title:
        text += title.lower() + " "
    if abstract:
        text += abstract.lower()
    return any(kw in text for kw in HIGH_RISK_KEYWORDS)


def classify_risk_level(
    risk_score: float,
    is_high_risk_keyword: bool,
    sentiment: str = "Neutral",
) -> str:
    """
    SAFE     — paper explicitly critiques / opposes the root paper (score = 0)
    HIGH     — score ≥ 3.0 OR systematic review that endorses
    MEDIUM   — score ≥ 1.5
    LOW      — score < 1.5
    """
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
    """
    Sort: SAFE papers last, then by risk_score desc → citation_count desc → depth asc.
    This surfaces the most dangerous contaminated papers at the top.
    """
    def key(p):
        sentiment = p.get("sentiment", "Neutral")
        is_safe   = 1 if sentiment == "Critiquing" else 0
        return (
            is_safe,
            -(p.get("risk_score") or 0.0),
            -(p.get("citation_count") or 0),
            p.get("depth_level") or 0,
        )
    return sorted(papers, key=key)


def compute_analytics(papers: list[dict]) -> dict:
    if not papers:
        return {
            "total": 0, "contaminated": 0, "safe": 0,
            "high_risk": 0, "medium_risk": 0, "low_risk": 0,
            "retracted_in_network": 0, "max_depth": 0,
            "by_level": {1: 0, 2: 0, 3: 0},
            "by_sentiment": {"Endorsing": 0, "Neutral": 0, "Critiquing": 0},
            "top10": [],
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

    # Top 10 = highest-risk non-safe papers
    risky = [p for p in papers if p.get("risk_level") not in ("SAFE",)]
    top10 = sorted(risky, key=lambda p: -(p.get("risk_score") or 0))[:10]

    return {
        "total":                total,
        "contaminated":         len(high) + len(medium),
        "safe":                 len(safe),
        "high_risk":            len(high),
        "medium_risk":          len(medium),
        "low_risk":             len(low),
        "retracted_in_network": len(retracted),
        "max_depth":            max_depth,
        "by_level":             by_level,
        "by_sentiment":         by_sentiment,
        "top10":                top10,
    }
