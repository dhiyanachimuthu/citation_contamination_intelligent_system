"""
Full analysis pipeline orchestrator.
Input: DOI → Output: complete contamination analysis result.
"""

import logging
from typing import Any, Callable
import networkx as nx

from .doi_validator import validate_doi
from .retraction_detector import check_retraction
from .graph_builder import build_citation_graph, get_node_depths
from .metadata_fetcher import fetch_metadata_batch
from .risk_engine import (
    compute_risk_score,
    is_high_risk_by_keywords,
    classify_risk_level,
    rank_papers,
    compute_analytics,
)

logger = logging.getLogger(__name__)


def run_analysis(
    doi_input: str,
    title_hint: str | None = None,
    progress_cb: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """
    Run the full citation contamination analysis pipeline.
    progress_cb(msg) is called at key steps to show real-time status.
    """
    def step(msg: str):
        logger.info(f"[Pipeline] {msg}")
        if progress_cb:
            progress_cb(msg)

    is_valid, root_doi = validate_doi(doi_input)
    if not is_valid:
        return {
            "success": False,
            "error": f"Invalid DOI format: '{doi_input}'",
            "root_doi": None,
            "retraction": {"is_retracted": False, "reason": None, "year": None},
            "graph": nx.DiGraph(),
            "papers": [],
            "analytics": {},
            "node_count": 0,
            "edge_count": 0,
        }

    step(f"Checking retraction status for {root_doi}…")
    retraction = check_retraction(root_doi, title=title_hint)
    status_msg = "RETRACTED" if retraction.get("is_retracted") else "not in retraction database"
    step(f"Retraction check complete: {status_msg}. Fetching forward citation graph…")

    graph = build_citation_graph(root_doi, progress_cb=progress_cb)
    depths = get_node_depths(graph)
    all_dois = list(graph.nodes)

    step(f"Graph built: {len(all_dois)} nodes. Enriching metadata from Semantic Scholar…")
    metadata_map = fetch_metadata_batch(all_dois)

    step("Computing contamination risk scores…")
    papers = []
    for doi in all_dois:
        if doi == root_doi:
            continue

        meta           = metadata_map.get(doi, {})
        depth          = depths.get(doi, 1)
        citation_count = meta.get("citation_count")
        title          = meta.get("title")
        abstract       = meta.get("abstract")
        authors        = meta.get("authors")
        year           = meta.get("year")

        doi_retraction   = check_retraction(doi)
        doi_is_retracted = doi_retraction.get("is_retracted", False)

        risk_score, sentiment = compute_risk_score(
            depth=depth,
            citation_count=citation_count,
            abstract=abstract,
            title=title,
            is_retracted=doi_is_retracted,
        )
        high_risk_keyword = is_high_risk_by_keywords(title, abstract)
        risk_level = classify_risk_level(risk_score, high_risk_keyword, sentiment)

        papers.append({
            "doi":               doi,
            "title":             title,
            "abstract":          abstract,
            "authors":           authors,
            "citation_count":    citation_count,
            "year":              year,
            "depth_level":       depth,
            "risk_score":        risk_score,
            "risk_level":        risk_level,
            "sentiment":         sentiment,
            "is_retracted":      doi_is_retracted,
            "high_risk_keyword": high_risk_keyword,
        })

    ranked = rank_papers(papers)

    # Root paper entry
    root_meta      = metadata_map.get(root_doi, {})
    root_rs, root_sent = compute_risk_score(
        depth=0,
        citation_count=root_meta.get("citation_count"),
        abstract=root_meta.get("abstract"),
        title=root_meta.get("title"),
        is_retracted=retraction.get("is_retracted", False),
    )
    root_entry = {
        "doi":               root_doi,
        "title":             root_meta.get("title"),
        "abstract":          root_meta.get("abstract"),
        "authors":           root_meta.get("authors"),
        "citation_count":    root_meta.get("citation_count"),
        "year":              root_meta.get("year"),
        "depth_level":       0,
        "risk_score":        root_rs,
        "risk_level":        "RETRACTED" if retraction.get("is_retracted") else classify_risk_level(
            root_rs,
            is_high_risk_by_keywords(root_meta.get("title"), root_meta.get("abstract")),
            root_sent,
        ),
        "sentiment":         root_sent,
        "is_retracted":      retraction.get("is_retracted", False),
        "high_risk_keyword": is_high_risk_by_keywords(root_meta.get("title"), root_meta.get("abstract")),
    }
    all_papers = [root_entry] + ranked
    retraction_year = retraction.get("year") if retraction.get("is_retracted") else None
    analytics  = compute_analytics(all_papers, retraction_year=retraction_year)

    step("Ranking complete. Preparing visualization…")

    return {
        "success":    True,
        "error":      None,
        "root_doi":   root_doi,
        "retraction": retraction,
        "graph":      graph,
        "papers":     all_papers,
        "analytics":  analytics,
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
    }
