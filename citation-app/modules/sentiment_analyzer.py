"""
Citation Context / Sentiment Analyzer.
Keyword-based classification into: Endorsing, Neutral, Critiquing.
Weights: Endorsing=1.5, Neutral=1.0, Critiquing=0.1

No ML required — deterministic, reproducible, fast.
"""

ENDORSING_KEYWORDS = [
    "confirm", "confirms", "confirmed", "support", "supports", "supported",
    "consistent with", "in agreement", "validate", "validates", "validated",
    "replicate", "replicates", "replicated", "demonstrate", "demonstrates",
    "demonstrate the same", "align", "aligns", "aligned with", "build on",
    "builds on", "extend", "extends", "as shown by", "as reported by",
    "as demonstrated by", "according to", "following", "based on",
    "corroborate", "corroborates", "adopts", "adopted",
]

CRITIQUING_KEYWORDS = [
    "contradict", "contradicts", "contradicted", "dispute", "disputes",
    "disputed", "challenge", "challenges", "challenged", "refute", "refutes",
    "refuted", "question", "questions", "questioned", "contrary to",
    "inconsistent with", "failed to replicate", "could not replicate",
    "does not support", "did not support", "unable to confirm", "retracted",
    "retraction", "error", "erratum", "correction", "flawed", "incorrect",
    "unreliable", "misleading", "fabricated", "manipulated",
]

SENTIMENT_WEIGHTS = {
    "Endorsing":  1.5,
    "Neutral":    1.0,
    "Critiquing": 0.1,
}


def classify_sentiment(abstract: str | None, title: str | None = None) -> str:
    """
    Classify citation sentiment from abstract/title text.
    Returns: 'Endorsing' | 'Neutral' | 'Critiquing'
    """
    text = ""
    if abstract:
        text += abstract.lower() + " "
    if title:
        text += title.lower()

    if not text.strip():
        return "Neutral"

    critique_hits = sum(1 for kw in CRITIQUING_KEYWORDS if kw in text)
    endorse_hits  = sum(1 for kw in ENDORSING_KEYWORDS  if kw in text)

    if critique_hits > endorse_hits:
        return "Critiquing"
    elif endorse_hits > 0:
        return "Endorsing"
    return "Neutral"


def get_sentiment_weight(sentiment: str) -> float:
    return SENTIMENT_WEIGHTS.get(sentiment, 1.0)
