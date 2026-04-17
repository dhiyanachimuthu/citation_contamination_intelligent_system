"""
Full analysis pipeline orchestrator.
Connects all modules end-to-end.
"""

import logging
from typing import Any
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
)

logger = logging.getLogger(__name__)


def run_analysis(doi_input: str, title_hint: str | None = None) -> dict[str, Any]:
    """
    Run the full citation contamination analysis.

    Returns a result dict:
        success: bool
        error: str | None
        root_doi: str | None
        retraction: dict
        graph: nx.DiGraph
        papers: list[dict]  — ranked paper records
        node_count: int
        edge_count: int
    """
    is_valid, root_doi = validate_doi(doi_input)
    if not is_valid:
        return {
            "success": False,
            "error": f"Invalid DOI format: '{doi_input}'",
            "root_doi": None,
            "retraction": {"is_retracted": False, "reason": None, "year": None},
            "graph": nx.DiGraph(),
            "papers": [],
            "node_count": 0,
            "edge_count": 0,
        }

    logger.info(f"Analyzing DOI: {root_doi}")

    retraction = check_retraction(root_doi, title=title_hint)
    logger.info(f"Retraction status: {retraction}")

    graph = build_citation_graph(root_doi)
    depths = get_node_depths(graph)

    all_dois = list(graph.nodes)

    logger.info(f"Fetching metadata for {len(all_dois)} DOIs...")
    metadata_map = fetch_metadata_batch(all_dois)

    papers = []
    for doi in all_dois:
        if doi == root_doi:
            continue

        meta = metadata_map.get(doi, {})
        depth = depths.get(doi, 1)
        citation_count = meta.get("citation_count")
        title = meta.get("title")
        abstract = meta.get("abstract")

        doi_retraction = check_retraction(doi)
        doi_is_retracted = doi_retraction.get("is_retracted", False)

        risk_score = compute_risk_score(
            depth=depth,
            citation_count=citation_count,
            is_retracted=doi_is_retracted,
        )
        high_risk_keyword = is_high_risk_by_keywords(title, abstract)
        risk_level = classify_risk_level(risk_score, high_risk_keyword)

        papers.append({
            "doi": doi,
            "title": title,
            "citation_count": citation_count,
            "year": meta.get("year"),
            "depth_level": depth,
            "risk_score": risk_score,
            "risk_level": risk_level,
            "is_retracted": doi_is_retracted,
            "high_risk_keyword": high_risk_keyword,
        })

    ranked = rank_papers(papers)

    root_meta = metadata_map.get(root_doi, {})
    root_risk = compute_risk_score(
        depth=0,
        citation_count=root_meta.get("citation_count"),
        is_retracted=retraction.get("is_retracted", False),
    )
    ranked.insert(0, {
        "doi": root_doi,
        "title": root_meta.get("title"),
        "citation_count": root_meta.get("citation_count"),
        "year": root_meta.get("year"),
        "depth_level": 0,
        "risk_score": root_risk,
        "risk_level": "HIGH" if retraction.get("is_retracted") else classify_risk_level(root_risk, False),
        "is_retracted": retraction.get("is_retracted", False),
        "high_risk_keyword": is_high_risk_by_keywords(root_meta.get("title"), root_meta.get("abstract")),
    })

    return {
        "success": True,
        "error": None,
        "root_doi": root_doi,
        "retraction": retraction,
        "graph": graph,
        "papers": ranked,
        "node_count": graph.number_of_nodes(),
        "edge_count": graph.number_of_edges(),
    }
