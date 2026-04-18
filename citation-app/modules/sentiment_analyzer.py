"""
Citation Sentiment Analyzer — Context-aware classification.

CORE LOGIC:
  A paper ENDORSES the root paper if it:
    - Replicates or confirms the same findings
    - Relies on the root paper's conclusions as valid evidence to support its own claims
    - Extends or builds on the root paper as credible prior work
    - Uses the root paper's framework without questioning it

  A paper CRITIQUES the root paper if it:
    - Shows negative/null results for the same intervention or hypothesis
    - Explicitly contradicts, challenges, or refutes the core claim
    - Is a higher-quality study (RCT/meta-analysis) that disproves an observational finding
    - Questions the methodology, data quality, or conclusions
    - Reports "no benefit", "no association", "not effective", etc.

  A paper is NEUTRAL if:
    - It cites the root paper as background context without relying on its conclusions
    - It studies a related topic without confirming or denying the core claim

WEIGHTS:
    Endorsing  = 1.5  (high contamination risk — treating invalid science as valid)
    Neutral    = 1.0  (moderate risk — indirect influence)
    Critiquing = 0.0  (no contamination — actively correcting the record)

Papers classified as Critiquing receive risk_level = SAFE regardless of citation count.
"""

# ── CRITIQUING patterns ────────────────────────────────────────────────────────
# Broad negative-result / opposition language found in scientific abstracts

CRITIQUE_STRONG = [
    # Direct contradiction
    "contrary to", "in contrast to", "in contrast with", "contradicts", "contradicted",
    "refutes", "refuted", "disproves", "disproved", "disputes", "disputed",
    "challenges", "challenged", "inconsistent with", "does not support",
    "did not support", "fails to support", "failed to support",
    "no evidence to support", "not supported by", "we found no evidence",

    # RCT / trial showing null/negative results
    "no significant difference", "no significant effect", "no significant benefit",
    "no significant improvement", "no significant reduction", "no significant association",
    "not statistically significant", "statistically nonsignificant",
    "primary endpoint was not met", "did not meet the primary endpoint",
    "primary outcome was not achieved", "failed to demonstrate",
    "failed to show", "failed to replicate", "could not replicate", "unable to replicate",
    "not effective", "was not effective", "no efficacy", "lack of efficacy",
    "no clinical benefit", "no virologic benefit", "no virologic cure",
    "no therapeutic benefit", "no survival benefit", "no mortality benefit",
    "no statistically significant", "no clear benefit", "no reduction in mortality",

    # Null/negative findings
    "no association", "no significant association", "no association was found",
    "no association between", "not associated with", "was not associated",
    "were not associated", "we found no association", "we observed no",
    "did not observe", "did not show", "did not find", "we did not find",
    "not demonstrate", "no improvement", "no reduction", "no benefit",
    "no effect", "no difference", "not superior", "was not superior",
    "not inferior", "non-inferior", "no advantage", "no added benefit",

    # Methodological critique
    "methodological flaw", "methodological concern", "methodological limitation",
    "selection bias", "confounding", "confounders", "uncontrolled confounding",
    "observational bias", "immortal time bias", "data integrity", "data manipulation",
    "fabricated", "falsified", "concerns about", "questions about the validity",
    "we question", "has been questioned", "expression of concern", "retraction",
    "retracted", "erratum", "correction issued", "cannot be trusted",
    "unreliable", "not reproducible", "failed to reproduce",

    # Opposing a specific drug / treatment claim
    "hydroxychloroquine was not", "hcq did not", "hcq was not effective",
    "no benefit from hydroxychloroquine", "ineffective",
]

CRITIQUE_MODERATE = [
    "although", "however", "nevertheless", "while previous", "unlike previous",
    "previous studies have suggested", "in contrast", "conversely",
    "mixed evidence", "conflicting evidence", "inconclusive", "insufficient evidence",
    "low-quality evidence", "very low certainty", "low certainty",
    "high risk of bias", "unclear evidence", "evidence is insufficient",
    "further research is needed", "limited evidence", "not conclusive",
    "remains unclear", "remains controversial", "debate", "disputed",
    "not proven", "unproven", "speculative",

    # Negative trial design markers (when paired with outcome language)
    "placebo-controlled", "double-blind", "double-blinded", "randomized controlled",
    "randomized trial", "sham-controlled", "blinded trial",
]

# ── ENDORSING patterns ─────────────────────────────────────────────────────────
ENDORSE_STRONG = [
    # Direct confirmation
    "confirms", "confirm", "confirmed", "consistent with previous", "in agreement with",
    "corroborates", "corroborate", "validates", "validate", "validated",
    "replicates", "replicated", "replicate", "we replicated", "consistent findings",
    "supports the hypothesis", "support the conclusion", "our findings support",
    "our results support", "our data support", "our study supports",
    "our findings are consistent with", "consistent with the finding",

    # Building on the cited paper
    "as shown by", "as reported by", "as demonstrated by", "as established by",
    "building on", "building upon", "extending the work", "extending the findings",
    "following the methodology", "following the approach", "adopting the framework",
    "based on the findings", "relying on", "drawing on",

    # Agreement with a specific claim
    "similar results", "similar findings", "similar outcomes", "similar conclusion",
    "similar effect", "similar efficacy", "significant benefit",
    "significant improvement", "significant reduction", "significant effect",
    "effective", "efficacious", "beneficial", "demonstrated benefit",
    "showed benefit", "showed improvement", "showed reduction",
]

ENDORSE_MODERATE = [
    "according to", "following", "based on", "as per", "as noted by",
    "as observed by", "as suggested by", "previous studies confirm",
    "prior research confirms", "earlier work shows",
]

SENTIMENT_WEIGHTS = {
    "Endorsing":  1.5,
    "Neutral":    1.0,
    "Critiquing": 0.0,   # Zero — opposing papers do NOT spread contamination
}


def classify_sentiment(abstract: str | None, title: str | None = None) -> str:
    """
    Classify how a citing paper uses the cited (root) paper's findings.

    Strategy:
    1. Count strong critique signals (negative results, direct opposition)
    2. Count strong endorsement signals (confirmation, replication, agreement)
    3. Moderate signals act as tiebreakers
    4. Default to Neutral if ambiguous

    Returns: 'Endorsing' | 'Neutral' | 'Critiquing'
    """
    text = ""
    if abstract:
        text += abstract.lower() + " "
    if title:
        text += title.lower()
    text = text.strip()

    if not text:
        return "Neutral"

    # Score strong signals
    critique_strong  = sum(1 for kw in CRITIQUE_STRONG  if kw in text)
    endorse_strong   = sum(1 for kw in ENDORSE_STRONG   if kw in text)
    critique_mod     = sum(1 for kw in CRITIQUE_MODERATE if kw in text)
    endorse_mod      = sum(1 for kw in ENDORSE_MODERATE  if kw in text)

    # Strong signals dominate
    if critique_strong > 0 and critique_strong >= endorse_strong:
        return "Critiquing"

    if endorse_strong > 0 and endorse_strong > critique_strong:
        # But override if there are also strong critique signals
        if critique_strong > 0:
            return "Neutral"
        return "Endorsing"

    # Fall back to moderate signals
    # Placebo-controlled trials are specifically providing independent evidence
    # Even with moderate signals, they tend toward critique unless strongly endorsing
    is_rct = any(kw in text for kw in [
        "randomized controlled trial", "randomised controlled trial",
        "placebo-controlled", "double-blind", "double-blinded",
        "randomized trial", "randomised trial",
    ])

    critique_score = critique_strong * 3 + critique_mod
    endorse_score  = endorse_strong * 3 + endorse_mod

    # RCTs with null-leaning language → Critique
    if is_rct and critique_mod > 0 and endorse_score == 0:
        return "Critiquing"

    if critique_score > endorse_score and critique_score > 0:
        return "Critiquing"
    elif endorse_score > critique_score and endorse_score > 0:
        return "Endorsing"

    return "Neutral"


def get_sentiment_weight(sentiment: str) -> float:
    return SENTIMENT_WEIGHTS.get(sentiment, 1.0)


def explain_sentiment(sentiment: str) -> str:
    """Human-readable explanation for the UI."""
    return {
        "Endorsing":  "Relies on or confirms the cited paper's findings (high contamination risk)",
        "Neutral":    "Cites the paper as context without strongly endorsing its conclusions",
        "Critiquing": "Opposes, refutes, or provides counter-evidence against the cited paper (SAFE)",
    }.get(sentiment, "")
