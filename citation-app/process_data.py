"""
Data Layer: Load retraction_watch.csv, extract valid DOIs,
normalize and store into processed_retractions.json.

Run once (or re-run to refresh):
    python process_data.py
"""

import os
import csv
import json
import re
import sys
import logging

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

DATA_DIR    = os.path.join(os.path.dirname(__file__), "data")
CSV_PATH    = os.path.join(DATA_DIR, "retraction_watch.csv")
OUTPUT_PATH = os.path.join(DATA_DIR, "processed_retractions.json")

DOI_RE = re.compile(r"^10\.\d{4,9}/[-._;()/:A-Z0-9a-z]+$", re.IGNORECASE)


def normalize_doi(raw: str) -> str | None:
    if not raw:
        return None
    doi = raw.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:", "DOI:"):
        if doi.startswith(prefix.lower()):
            doi = doi[len(prefix):]
    doi = doi.strip()
    return doi if DOI_RE.match(doi) else None


def extract_year(raw: str | None) -> int | None:
    if not raw:
        return None
    for part in str(raw).replace("-", "/").split("/"):
        try:
            y = int(part.strip())
            if 1900 < y < 2100:
                return y
        except ValueError:
            continue
    return None


def process():
    if not os.path.exists(CSV_PATH):
        logger.error(f"CSV not found: {CSV_PATH}")
        sys.exit(1)

    logger.info(f"Reading {CSV_PATH} …")
    records: dict[str, dict] = {}
    no_doi_records: list[dict] = []
    skipped = 0
    total = 0

    with open(CSV_PATH, encoding="utf-8", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            total += 1
            raw_doi = (
                row.get("OriginalPaperDOI")
                or row.get("DOI")
                or row.get("doi")
                or ""
            )
            doi = normalize_doi(raw_doi)

            reason = (
                row.get("Reason")
                or row.get("RetractionReason")
                or row.get("reason")
                or None
            )
            year_raw = (
                row.get("RetractionDate")
                or row.get("Year")
                or row.get("year")
                or None
            )
            year = extract_year(year_raw)
            title = (row.get("Title") or row.get("title") or "").strip() or None

            entry = {
                "is_retracted": True,
                "reason": str(reason).strip() if reason else None,
                "year": year,
                "title": title,
            }

            if doi:
                records[doi] = entry
            else:
                if title:
                    no_doi_records.append(entry)
                else:
                    skipped += 1

    os.makedirs(DATA_DIR, exist_ok=True)
    output = {
        "by_doi": records,
        "no_doi": no_doi_records,
        "stats": {
            "total_rows": total,
            "with_doi": len(records),
            "without_doi": len(no_doi_records),
            "skipped": skipped,
        },
    }

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)

    logger.info(
        f"Done. Total rows: {total} | With DOI: {len(records)} | "
        f"Without DOI (title only): {len(no_doi_records)} | Skipped: {skipped}"
    )
    logger.info(f"Written to: {OUTPUT_PATH}")
    return output


if __name__ == "__main__":
    process()
