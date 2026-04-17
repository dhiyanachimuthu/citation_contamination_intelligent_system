"""
Contamination Risk Engine.
Full formula: risk_score = depth_weight × sentiment_weight × log(1 + citation_count)
Retracted papers: risk_score × 2.0
"""

import math
import logging

from .sentiment_analyzer import classify_sentiment, get_sentiment_weight

logger = logging.getLogger(__name__)

DEPTH_WEIGHTS = {0: 0.0, 1: 1.0, 2: 0.5, 3: 0.2}
RETRACTED_MULTIPLIER = 2.0

HIGH_RISK_KEYWORDS = ["systematic review", "meta-analysis", "review", "meta analysis"]

FIELD_VELOCITY = {
    "medicine":    1.3,
    "biology":     1.1,
    "chemistry":   1.0,
    "physics":     0.9,
    "psychology":  1.2,
    "mathematics": 0.7,
    "computer":    1.0,
}


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

    Formula:
        depth_weight     = {1: 1.0, 2: 0.5, 3: 0.2}
        sentiment_weight = {Endorsing: 1.5, Neutral: 1.0, Critiquing: 0.1}
        influence        = log(1 + citation_count)
        risk_score       = depth_weight × sentiment_weight × influence
        if retracted → × 2.0
    """
    depth_weight = DEPTH_WEIGHTS.get(depth, 0.1)
    cc = citation_count if citation_count is not None else 0
    influence = math.log1p(cc)

    sentiment = classify_sentiment(abstract, title)
    sentiment_weight = get_sentiment_weight(sentiment)

    score = depth_weight * sentiment_weight * influence

    if is_retracted:
        score *= RETRACTED_MULTIPLIER

    return round(score, 4), sentiment


def is_high_risk_by_keywords(title: str | None, abstract: str | None) -> bool:
    """Keyword-based high-risk classification — no semantic reasoning."""
    text = ""
    if title:
        text += title.lower() + " "
    if abstract:
        text += abstract.lower()
    return any(kw in text for kw in HIGH_RISK_KEYWORDS)


def classify_risk_level(risk_score: float, is_high_risk_keyword: bool) -> str:
    if is_high_risk_keyword or risk_score >= 3.0:
        return "HIGH"
    elif risk_score >= 1.5:
        return "MEDIUM"
    return "LOW"


def rank_papers(papers: list[dict]) -> list[dict]:
    """Deterministic sort: risk_score desc → citation_count desc → depth asc."""
    def key(p):
        return (-(p.get("risk_score") or 0.0), -(p.get("citation_count") or 0), p.get("depth_level") or 0)
    return sorted(papers, key=key)


def compute_analytics(papers: list[dict]) -> dict:
    """Compute analytics summary over all papers."""
    if not papers:
        return {
            "total": 0, "contaminated": 0, "high_risk": 0, "medium_risk": 0, "low_risk": 0,
            "retracted_in_network": 0, "max_depth": 0,
            "by_level": {1: 0, 2: 0, 3: 0},
            "by_sentiment": {"Endorsing": 0, "Neutral": 0, "Critiquing": 0},
            "top10": [],
        }

    total = len(papers)
    high   = [p for p in papers if p.get("risk_level") == "HIGH"]
    medium = [p for p in papers if p.get("risk_level") == "MEDIUM"]
    low    = [p for p in papers if p.get("risk_level") == "LOW"]
    retracted = [p for p in papers if p.get("is_retracted")]

    by_level = {1: 0, 2: 0, 3: 0}
    by_sentiment = {"Endorsing": 0, "Neutral": 0, "Critiquing": 0}
    max_depth = 0

    for p in papers:
        d = p.get("depth_level", 0)
        if d in by_level:
            by_level[d] += 1
        if d > max_depth:
            max_depth = d
        s = p.get("sentiment", "Neutral")
        if s in by_sentiment:
            by_sentiment[s] += 1

    top10 = sorted(papers, key=lambda p: -(p.get("risk_score") or 0))[:10]

    return {
        "total": total,
        "contaminated": len(high) + len(medium),
        "high_risk": len(high),
        "medium_risk": len(medium),
        "low_risk": len(low),
        "retracted_in_network": len(retracted),
        "max_depth": max_depth,
        "by_level": by_level,
        "by_sentiment": by_sentiment,
        "top10": top10,
    }
