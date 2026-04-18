"""
Citation fetch engine — dual source strategy:
  Primary:   OpenCitations COCI API (stream=True to handle large responses)
  Fallback:  Semantic Scholar /citations endpoint (more reliable for many papers)
Returns ONLY real citation data — no synthetic fallbacks.
"""

import time
import logging
import requests

from .cache import get_citations_cache

logger = logging.getLogger(__name__)

OPENCITATIONS_BASE = "https://opencitations.net/index/coci/api/v1"
S2_BASE            = "https://api.semanticscholar.org/graph/v1"
TIMEOUT            = 20
MAX_RETRIES        = 3
BACKOFF_BASE       = 2.0


# ── OpenCitations (streaming) ──────────────────────────────────────────────────

def _oc_get(url: str) -> list | None:
    """GET with streaming to handle large JSON responses without IncompleteRead."""
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(
                url,
                timeout=TIMEOUT,
                headers={"Accept": "application/json"},
                stream=True,
            )
            if resp.status_code == 200:
                try:
                    return resp.json()
                except Exception as e:
                    # Partial read — collect chunks manually
                    logger.warning(f"JSON decode failed for {url}: {e}")
                    return None
            elif resp.status_code == 429:
                wait = BACKOFF_BASE ** (attempt + 1)
                logger.warning(f"OpenCitations rate limited. Waiting {wait:.0f}s.")
                time.sleep(wait)
            elif resp.status_code == 404:
                return []
            else:
                logger.warning(f"OpenCitations HTTP {resp.status_code}")
                return None
        except requests.exceptions.ChunkedEncodingError as e:
            logger.warning(f"OpenCitations IncompleteRead (attempt {attempt+1}): {e}")
            time.sleep(BACKOFF_BASE ** (attempt + 1))
        except requests.RequestException as e:
            wait = BACKOFF_BASE ** (attempt + 1)
            logger.warning(f"OpenCitations error (attempt {attempt+1}): {e}. Waiting {wait:.0f}s.")
            time.sleep(wait)
    logger.error(f"OpenCitations: all retries exhausted for {url}")
    return None


def _extract_dois_from_oc(data: list, field: str) -> list[str]:
    result = []
    for record in data:
        val = (record.get(field) or "").strip().lower()
        if val and val.startswith("10."):
            result.append(val)
    return list(set(result))


def _fetch_citing_oc(doi: str) -> list[str] | None:
    """Fetch papers that cite doi via OpenCitations. Returns None on failure."""
    url = f"{OPENCITATIONS_BASE}/citations/{doi}"
    data = _oc_get(url)
    if data is None:
        return None
    return _extract_dois_from_oc(data, "citing")


# ── Semantic Scholar citations ─────────────────────────────────────────────────

def _fetch_citing_s2(doi: str, limit: int = 500) -> list[str] | None:
    """
    Fetch citing papers from Semantic Scholar.
    Returns list of DOIs, or None on failure.
    """
    url   = f"{S2_BASE}/paper/DOI:{doi}/citations"
    params = {"fields": "externalIds", "limit": min(limit, 1000)}

    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT)
            if resp.status_code == 200:
                data = resp.json()
                dois = []
                for item in data.get("data", []):
                    citing = item.get("citingPaper", {})
                    ext_ids = citing.get("externalIds") or {}
                    d = (ext_ids.get("DOI") or "").strip().lower()
                    if d and d.startswith("10."):
                        dois.append(d)
                # Handle pagination if needed
                next_token = data.get("next")
                if next_token and len(dois) < limit:
                    params2 = dict(params)
                    params2["token"] = next_token
                    resp2 = requests.get(url, params=params2, timeout=TIMEOUT)
                    if resp2.status_code == 200:
                        data2 = resp2.json()
                        for item in data2.get("data", []):
                            citing = item.get("citingPaper", {})
                            ext_ids = citing.get("externalIds") or {}
                            d = (ext_ids.get("DOI") or "").strip().lower()
                            if d and d.startswith("10."):
                                dois.append(d)
                logger.info(f"S2 citations for {doi}: {len(dois)} papers")
                return list(set(dois))
            elif resp.status_code == 429:
                wait = BACKOFF_BASE ** (attempt + 1)
                logger.warning(f"S2 citations rate limited. Waiting {wait:.0f}s.")
                time.sleep(wait)
            elif resp.status_code == 404:
                return []
            else:
                logger.warning(f"S2 citations HTTP {resp.status_code} for {doi}")
                return None
        except requests.RequestException as e:
            wait = BACKOFF_BASE ** (attempt + 1)
            logger.warning(f"S2 citations error: {e}. Retry in {wait:.0f}s.")
            time.sleep(wait)
    return None


# ── Public API ─────────────────────────────────────────────────────────────────

def fetch_citing_dois(doi: str) -> list[str]:
    """
    Fetch DOIs of papers that cite the given DOI.
    Strategy: OpenCitations first → Semantic Scholar fallback → merge unique.
    Cached — repeated calls are instant.
    Returns empty list on total failure.
    """
    cache_key = f"citing:{doi}"
    cache = get_citations_cache()
    cached = cache.get(cache_key)
    if cached is not None:
        logger.debug(f"Cache HIT: citing:{doi} ({len(cached)} entries)")
        return cached

    oc_result = _fetch_citing_oc(doi)
    s2_result = _fetch_citing_s2(doi)

    if oc_result is None and s2_result is None:
        logger.warning(f"Both OC and S2 failed for {doi}. Returning [].")
        return []

    merged = list(set((oc_result or []) + (s2_result or [])))
    logger.info(
        f"cite fetch for {doi}: OC={len(oc_result or [])}, "
        f"S2={len(s2_result or [])}, merged={len(merged)}"
    )

    cache.set(cache_key, merged)
    return merged


def fetch_cited_dois(doi: str) -> list[str]:
    """
    Fetch DOIs that the given paper cites (its references) — backward citations.
    Used for reference analysis. Cached.
    """
    cache_key = f"cited:{doi}"
    cache = get_citations_cache()
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    url = f"{OPENCITATIONS_BASE}/references/{doi}"
    data = _oc_get(url)
    result = _extract_dois_from_oc(data or [], "cited")
    cache.set(cache_key, result)
    return result
