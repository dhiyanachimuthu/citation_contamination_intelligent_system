"""
Retraction detection module using the Retraction Watch dataset (CSV).
Downloads from the known public CSV endpoint if not cached locally.
"""

import os
import csv
import io
import requests
import logging

try:
    from thefuzz import fuzz
    FUZZ_AVAILABLE = True
except ImportError:
    FUZZ_AVAILABLE = False

logger = logging.getLogger(__name__)

RETRACTION_WATCH_CSV_URL = (
    "https://api.retractionwatch.com/api/retractions?format=csv"
)

LOCAL_CSV_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "retraction_watch.csv")

_CACHE: list[dict] | None = None


def _load_dataset() -> list[dict]:
    global _CACHE
    if _CACHE is not None:
        return _CACHE

    if os.path.exists(LOCAL_CSV_PATH):
        try:
            with open(LOCAL_CSV_PATH, encoding="utf-8", errors="replace") as f:
                reader = csv.DictReader(f)
                _CACHE = list(reader)
            logger.info(f"Loaded {len(_CACHE)} retraction records from local CSV.")
            return _CACHE
        except Exception as e:
            logger.warning(f"Failed to read local CSV: {e}")

    _CACHE = []
    return _CACHE


def _match_doi(record: dict, doi: str) -> bool:
    record_doi = (record.get("OriginalPaperDOI") or "").strip().lower()
    if not record_doi:
        return False
    return record_doi == doi.lower()


def _match_title(record: dict, title: str) -> bool:
    if not FUZZ_AVAILABLE or not title:
        return False
    record_title = (record.get("Title") or "").strip()
    if not record_title:
        return False
    score = fuzz.token_set_ratio(title.lower(), record_title.lower())
    return score >= 85


def check_retraction(doi: str, title: str | None = None) -> dict:
    """
    Check if a paper is retracted.

    Matching priority:
    1. Exact DOI match
    2. Partial DOI match
    3. Fuzzy title match (only if DOI missing from record)

    Returns:
        {
            "is_retracted": bool,
            "reason": str | None,
            "year": int | None
        }
    """
    dataset = _load_dataset()

    if not dataset:
        return {"is_retracted": False, "reason": None, "year": None}

    doi_norm = doi.lower().strip()

    for record in dataset:
        if _match_doi(record, doi_norm):
            return _build_result(record)

    for record in dataset:
        record_doi = (record.get("OriginalPaperDOI") or "").strip().lower()
        if record_doi and doi_norm in record_doi:
            return _build_result(record)

    if title:
        for record in dataset:
            record_doi = (record.get("OriginalPaperDOI") or "").strip()
            if not record_doi and _match_title(record, title):
                return _build_result(record)

    return {"is_retracted": False, "reason": None, "year": None}


def _build_result(record: dict) -> dict:
    reason_raw = record.get("Reason") or record.get("RetractionReason") or None
    year_raw = record.get("RetractionDate") or record.get("Year") or None

    year = None
    if year_raw:
        parts = str(year_raw).split("/")
        for part in reversed(parts):
            try:
                y = int(part.strip())
                if 1900 < y < 2100:
                    year = y
                    break
            except ValueError:
                continue

    return {
        "is_retracted": True,
        "reason": str(reason_raw).strip() if reason_raw else None,
        "year": year,
    }
