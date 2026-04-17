import re


DOI_PATTERN = re.compile(
    r'^10\.\d{4,9}/[-._;()/:A-Z0-9a-z]+$',
    re.IGNORECASE
)

DOI_PREFIXES = [
    "https://doi.org/",
    "http://doi.org/",
    "https://dx.doi.org/",
    "http://dx.doi.org/",
    "doi:",
    "DOI:",
]


def normalize_doi(doi: str) -> str | None:
    """
    Normalize a DOI string: strip prefixes, lowercase, strip whitespace.
    Returns None if input is empty or None.
    """
    if not doi:
        return None
    doi = doi.strip()
    for prefix in DOI_PREFIXES:
        if doi.lower().startswith(prefix.lower()):
            doi = doi[len(prefix):]
            break
    return doi.lower().strip()


def validate_doi(doi: str) -> tuple[bool, str | None]:
    """
    Validate and normalize a DOI string.
    Returns (is_valid, normalized_doi).
    normalized_doi is None if invalid.
    """
    normalized = normalize_doi(doi)
    if not normalized:
        return False, None
    if DOI_PATTERN.match(normalized):
        return True, normalized
    return False, None
