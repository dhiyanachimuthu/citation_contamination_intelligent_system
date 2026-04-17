"""
Citation fetch engine using the OpenCitations COCI API.
Disk-cached to reduce redundant API calls across runs.
Returns ONLY real citation data — no synthetic fallbacks.
"""

import time
import logging
import requests

from .cache import get_citations_cache

logger = logging.getLogger(__name__)

OPENCITATIONS_BASE = "https://opencitations.net/index/coci/api/v1"
TIMEOUT     = 15
MAX_RETRIES = 3
BACKOFF_BASE = 2.0


def _get_with_retry(url: str) -> list | None:
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, timeout=TIMEOUT, headers={"Accept": "application/json"})
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = BACKOFF_BASE ** (attempt + 1)
                logger.warning(f"Rate limited by OpenCitations. Waiting {wait:.0f}s.")
                time.sleep(wait)
            elif resp.status_code == 404:
                return []
            else:
                logger.warning(f"OpenCitations HTTP {resp.status_code} for {url}")
                return None
        except requests.RequestException as e:
            wait = BACKOFF_BASE ** (attempt + 1)
            logger.warning(f"OpenCitations request error ({e}). Retry in {wait:.0f}s.")
            time.sleep(wait)
    logger.error(f"OpenCitations: all retries exhausted for {url}")
    return None


def _extract_dois(data: list, field: str) -> list[str]:
    result = []
    for record in data:
        val = (record.get(field) or "").strip().lower()
        if val and val.startswith("10."):
            result.append(val)
    return list(set(result))


def fetch_citing_dois(doi: str) -> list[str]:
    """
    Fetch DOIs of papers that cite the given DOI.
    Cached — repeated calls return the cached result instantly.
    Returns empty list on failure — never fake data.
    """
    cache_key = f"citing:{doi}"
    cache = get_citations_cache()
    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug(f"Cache HIT: citing:{doi} ({len(cached)} entries)")
        return cached

    url = f"{OPENCITATIONS_BASE}/citations/{doi}"
    data = _get_with_retry(url)

    if data is None:
        return []

    result = _extract_dois(data, "citing")
    cache.set(cache_key, result)
    logger.info(f"OpenCitations: {len(result)} citers of {doi}")
    return result


def fetch_cited_dois(doi: str) -> list[str]:
    """
    Fetch DOIs that the given paper cites (its references).
    Cached. Returns empty list on failure.
    """
    cache_key = f"cited:{doi}"
    cache = get_citations_cache()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"{OPENCITATIONS_BASE}/references/{doi}"
    data = _get_with_retry(url)

    if data is None:
        return []

    result = _extract_dois(data, "cited")
    cache.set(cache_key, result)
    return result
