"""
Retraction detection module.
Primary source: processed_retractions.json (pre-processed from Retraction Watch CSV).
Falls back to raw CSV scan if JSON not yet generated.
"""

import os
import json
import csv
import logging

try:
    from thefuzz import fuzz
    FUZZ_AVAILABLE = True
except ImportError:
    FUZZ_AVAILABLE = False

logger = logging.getLogger(__name__)

DATA_DIR        = os.path.join(os.path.dirname(__file__), "..", "data")
PROCESSED_PATH  = os.path.join(DATA_DIR, "processed_retractions.json")
RAW_CSV_PATH    = os.path.join(DATA_DIR, "retraction_watch.csv")

_PROCESSED: dict | None = None


def _load_processed() -> dict:
    global _PROCESSED
    if _PROCESSED is not None:
        return _PROCESSED

    if os.path.exists(PROCESSED_PATH):
        try:
            with open(PROCESSED_PATH, encoding="utf-8") as f:
                _PROCESSED = json.load(f)
            stats = _PROCESSED.get("stats", {})
            logger.info(
                f"Loaded processed_retractions.json: "
                f"{stats.get('with_doi', 0)} DOIs, "
                f"{stats.get('without_doi', 0)} title-only entries."
            )
            return _PROCESSED
        except Exception as e:
            logger.warning(f"Failed to load processed JSON: {e}")

    # Fallback: trigger processing on first use
    if os.path.exists(RAW_CSV_PATH):
        logger.info("processed_retractions.json not found — running data processing now.")
        try:
            import sys
            sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
            from process_data import process
            _PROCESSED = process()
            return _PROCESSED
        except Exception as e:
            logger.error(f"Data processing failed: {e}")

    _PROCESSED = {"by_doi": {}, "no_doi": []}
    return _PROCESSED


def check_retraction(doi: str, title: str | None = None) -> dict:
    """
    Check if a paper is retracted.

    Matching priority:
    1. Exact DOI match in processed index
    2. Fuzzy title match (title-only records, only if title provided)

    Returns:
        {"is_retracted": bool, "reason": str|None, "year": int|None}
    """
    data = _load_processed()
    doi_norm = doi.strip().lower()

    # 1. Exact DOI lookup — O(1)
    by_doi = data.get("by_doi", {})
    if doi_norm in by_doi:
        entry = by_doi[doi_norm]
        return {
            "is_retracted": True,
            "reason": entry.get("reason"),
            "year": entry.get("year"),
        }

    # 2. Fuzzy title match (only for records with no DOI)
    if title and FUZZ_AVAILABLE:
        title_lower = title.lower()
        for entry in data.get("no_doi", []):
            record_title = (entry.get("title") or "").lower()
            if not record_title:
                continue
            score = fuzz.token_set_ratio(title_lower, record_title)
            if score >= 88:
                return {
                    "is_retracted": True,
                    "reason": entry.get("reason"),
                    "year": entry.get("year"),
                }

    return {"is_retracted": False, "reason": None, "year": None}
