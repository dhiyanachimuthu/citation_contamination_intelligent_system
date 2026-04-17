"""
Metadata enrichment module using Semantic Scholar API.
Returns NULL for missing fields — never infers or guesses.
"""

import time
import logging
import requests

logger = logging.getLogger(__name__)

S2_BASE = "https://api.semanticscholar.org/graph/v1"
FIELDS = "title,abstract,citationCount,year,externalIds"
TIMEOUT = 15
MAX_RETRIES = 3
BACKOFF_BASE = 2.0


def _get_with_retry(url: str, params: dict | None = None) -> dict | None:
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = BACKOFF_BASE ** (attempt + 1)
                logger.warning(f"Rate limited by S2. Waiting {wait}s.")
                time.sleep(wait)
            elif resp.status_code == 404:
                return None
            else:
                logger.warning(f"S2 HTTP {resp.status_code} for {url}")
                return None
        except requests.RequestException as e:
            wait = BACKOFF_BASE ** (attempt + 1)
            logger.warning(f"S2 request error ({e}). Waiting {wait}s.")
            time.sleep(wait)
    return None


def fetch_metadata(doi: str) -> dict:
    """
    Fetch paper metadata from Semantic Scholar by DOI.

    Returns dict with fields:
        title: str | None
        abstract: str | None
        citation_count: int | None
        year: int | None

    Missing fields are NULL — never approximated.
    """
    url = f"{S2_BASE}/paper/DOI:{doi}"
    data = _get_with_retry(url, params={"fields": FIELDS})

    if not data:
        return {
            "title": None,
            "abstract": None,
            "citation_count": None,
            "year": None,
        }

    title = data.get("title") or None
    abstract = data.get("abstract") or None
    citation_count = data.get("citationCount")
    if citation_count is not None:
        try:
            citation_count = int(citation_count)
        except (ValueError, TypeError):
            citation_count = None
    year = data.get("year")
    if year is not None:
        try:
            year = int(year)
        except (ValueError, TypeError):
            year = None

    return {
        "title": title,
        "abstract": abstract,
        "citation_count": citation_count,
        "year": year,
    }


def fetch_metadata_batch(dois: list[str]) -> dict[str, dict]:
    """
    Fetch metadata for a batch of DOIs.
    Returns a dict mapping DOI -> metadata dict.
    """
    results = {}
    for doi in dois:
        results[doi] = fetch_metadata(doi)
        time.sleep(0.1)
    return results
