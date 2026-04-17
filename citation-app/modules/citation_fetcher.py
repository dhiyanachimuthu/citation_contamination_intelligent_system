"""
Citation fetch engine using the OpenCitations API.
Returns ONLY real citation data — no synthetic fallbacks.
"""

import time
import logging
import requests

logger = logging.getLogger(__name__)

OPENCITATIONS_BASE = "https://opencitations.net/index/coci/api/v1"
TIMEOUT = 15
MAX_RETRIES = 3
BACKOFF_BASE = 2.0


def _get_with_retry(url: str, params: dict | None = None) -> dict | list | None:
    for attempt in range(MAX_RETRIES):
        try:
            resp = requests.get(url, params=params, timeout=TIMEOUT)
            if resp.status_code == 200:
                return resp.json()
            elif resp.status_code == 429:
                wait = BACKOFF_BASE ** (attempt + 1)
                logger.warning(f"Rate limited. Waiting {wait}s before retry.")
                time.sleep(wait)
            else:
                logger.warning(f"HTTP {resp.status_code} from {url}")
                return None
        except requests.RequestException as e:
            wait = BACKOFF_BASE ** (attempt + 1)
            logger.warning(f"Request error ({e}). Waiting {wait}s before retry.")
            time.sleep(wait)
    return None


def fetch_citing_dois(doi: str) -> list[str]:
    """
    Fetch the list of DOIs that cite the given DOI.
    Returns only real DOIs from OpenCitations API.
    Returns empty list on failure — never fake data.
    """
    url = f"{OPENCITATIONS_BASE}/citations/{doi}"
    data = _get_with_retry(url)

    if not data or not isinstance(data, list):
        return []

    citing_dois = []
    for record in data:
        citing = record.get("citing") or ""
        citing = citing.strip().lower()
        if citing and citing.startswith("10."):
            citing_dois.append(citing)

    return list(set(citing_dois))


def fetch_cited_by_dois(doi: str) -> list[str]:
    """
    Fetch DOIs cited by the given paper (references).
    Returns empty list on failure.
    """
    url = f"{OPENCITATIONS_BASE}/references/{doi}"
    data = _get_with_retry(url)

    if not data or not isinstance(data, list):
        return []

    cited_dois = []
    for record in data:
        cited = record.get("cited") or ""
        cited = cited.strip().lower()
        if cited and cited.startswith("10."):
            cited_dois.append(cited)

    return list(set(cited_dois))
