"""
Metadata enrichment using Semantic Scholar API.
Disk-cached. Returns NULL for any missing field — never infers or guesses.
"""

import time
import logging
import requests

from .cache import get_metadata_cache

logger = logging.getLogger(__name__)

S2_BASE  = "https://api.semanticscholar.org/graph/v1"
FIELDS   = "title,abstract,citationCount,year,authors"
TIMEOUT  = 15
MAX_RETRIES  = 3
BACKOFF_BASE = 2.0
BATCH_DELAY  = 0.12   # seconds between requests to stay under rate limit


def _get_with_retry(url: str, params: dict | None = None) -> dict | None:
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = BACKOFF_BASE ** (attempt + 1)
                logger.warning(f"S2 rate limited. Waiting {wait:.0f}s.")
                time.sleep(wait)
            elif resp.status_code == 404:
                return None
            else:
                logger.warning(f"S2 HTTP {resp.status_code} for {url}")
                return None
        except requests.RequestException as e:
            wait = BACKOFF_BASE ** (attempt + 1)
            logger.warning(f"S2 request error ({e}). Retry in {wait:.0f}s.")
            time.sleep(wait)
    return None


def _parse_response(data: dict | None) -> dict:
    if not data:
        return {"title": None, "abstract": None, "citation_count": None, "year": None, "authors": None}

    title  = data.get("title") or None
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

    authors_raw = data.get("authors") or []
    if authors_raw:
        authors = [a.get("name") for a in authors_raw if a.get("name")][:5] or None
    else:
        authors = None

    return {
        "title": title,
        "abstract": abstract,
        "citation_count": citation_count,
        "year": year,
        "authors": authors,
    }


def fetch_metadata(doi: str) -> dict:
    """
    Fetch metadata for a single DOI from Semantic Scholar.
    Missing fields are NULL — never approximated.
    """
    cache = get_metadata_cache()
    cached = cache.get(doi)
    if cached is not None:
        logger.debug(f"Metadata cache HIT: {doi}")
        return cached

    url = f"{S2_BASE}/paper/DOI:{doi}"
    data = _get_with_retry(url, params={"fields": FIELDS})
    result = _parse_response(data)

    cache.set(doi, result)
    return result


def fetch_metadata_batch(dois: list[str]) -> dict[str, dict]:
    """
    Fetch metadata for a list of DOIs.
    Returns dict mapping DOI -> metadata.
    Uses cache aggressively; only calls API for uncached DOIs.
    """
    cache = get_metadata_cache()
    results: dict[str, dict] = {}
    uncached: list[str] = []

    for doi in dois:
        hit = cache.get(doi)
        if hit is not None:
            results[doi] = hit
        else:
            uncached.append(doi)

    logger.info(f"Metadata: {len(results)} cache hits, {len(uncached)} API calls needed.")

    for doi in uncached:
        url = f"{S2_BASE}/paper/DOI:{doi}"
        data = _get_with_retry(url, params={"fields": FIELDS})
        parsed = _parse_response(data)
        cache.set(doi, parsed)
        results[doi] = parsed
        time.sleep(BATCH_DELAY)

    return results
