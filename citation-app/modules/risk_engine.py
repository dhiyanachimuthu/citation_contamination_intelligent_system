"""
Contamination Risk Engine — rule-based only, no ML.
Implements the exact formula from spec.
"""

import math
import logging

logger = logging.getLogger(__name__)

DEPTH_WEIGHTS = {
    1: 1.0,
    2: 0.5,
    3: 0.2,
}

RETRACTED_MULTIPLIER = 2.0

HIGH_RISK_KEYWORDS = [
    "systematic review",
    "meta-analysis",
    "review",
]


def compute_risk_score(
    depth: int,
    citation_count: int | None,
    is_retracted: bool = False,
) -> float:
    """
    Compute contamination risk score.

    Formula:
        depth_weight = {1: 1.0, 2: 0.5, 3: 0.2}
        influence = log(1 + citation_count)
        risk_score = depth_weight * influence
        if retracted: risk_score *= 2.0
    """
    depth_weight = DEPTH_WEIGHTS.get(depth, 0.1)
    cc = citation_count if citation_count is not None else 0
    influence = math.log1p(cc)
    score = depth_weight * influence
    if is_retracted:
        score *= RETRACTED_MULTIPLIER
    return round(score, 4)


def is_high_risk_by_keywords(title: str | None, abstract: str | None) -> bool:
    """
    Keyword-based high risk classification only.
    No semantic reasoning.
    """
    text = ""
    if title:
        text += title.lower() + " "
    if abstract:
        text += abstract.lower()

    for keyword in HIGH_RISK_KEYWORDS:
        if keyword in text:
            return True
    return False


def classify_risk_level(risk_score: float, is_high_risk_keyword: bool) -> str:
    """
    Classify into risk level string based on score and keyword flag.
    """
    if is_high_risk_keyword or risk_score >= 3.0:
        return "HIGH"
    elif risk_score >= 1.5:
        return "MEDIUM"
    else:
        return "LOW"


def rank_papers(papers: list[dict]) -> list[dict]:
    """
    Sort papers deterministically by:
    1. risk_score (descending)
    2. citation_count (descending)
    3. depth_level (ascending)

    Input: list of dicts with keys: doi, risk_score, citation_count, depth_level
    """
    def sort_key(p: dict):
        return (
            -(p.get("risk_score") or 0.0),
            -(p.get("citation_count") or 0),
            (p.get("depth_level") or 0),
        )

    return sorted(papers, key=sort_key)
