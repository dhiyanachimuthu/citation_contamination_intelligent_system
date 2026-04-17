"""
Graph builder module — builds a directed citation graph from real API data only.
Enforces hard caps, visited tracking, deduplication, and no fake nodes.
"""

import logging
from collections import deque
import networkx as nx

from .citation_fetcher import fetch_citing_dois

logger = logging.getLogger(__name__)

MAX_NODES = 150
MAX_HOPS = 3


def _normalize_doi(doi: str) -> str:
    return doi.strip().lower()


def build_citation_graph(
    root_doi: str,
    max_nodes: int = MAX_NODES,
    max_hops: int = MAX_HOPS,
) -> nx.DiGraph:
    """
    Build a directed citation graph starting from root_doi.
    Nodes are real DOIs. Edges represent real citation relationships.
    Papers citing root_doi are included (citing -> root).

    Returns a nx.DiGraph with node attributes:
        depth: int (hop level from root)
    """
    graph = nx.DiGraph()
    visited: set[str] = set()
    queue: deque[tuple[str, int]] = deque()

    root = _normalize_doi(root_doi)
    graph.add_node(root, depth=0)
    visited.add(root)
    queue.append((root, 0))

    while queue and graph.number_of_nodes() < max_nodes:
        current_doi, depth = queue.popleft()

        if depth >= max_hops:
            continue

        citing_dois = fetch_citing_dois(current_doi)
        logger.info(f"DOI {current_doi} (depth {depth}): {len(citing_dois)} citing papers.")

        for citing_doi in citing_dois:
            if graph.number_of_nodes() >= max_nodes:
                logger.info(f"Node cap ({max_nodes}) reached. Stopping expansion.")
                break

            norm = _normalize_doi(citing_doi)
            if not norm or not norm.startswith("10."):
                continue

            if norm == current_doi:
                continue

            if norm not in visited:
                visited.add(norm)
                graph.add_node(norm, depth=depth + 1)
                queue.append((norm, depth + 1))

            if not graph.has_edge(norm, current_doi):
                graph.add_edge(norm, current_doi)

    invalid_nodes = [n for n in list(graph.nodes) if not str(n).startswith("10.")]
    for n in invalid_nodes:
        logger.warning(f"Removing invalid node: {n}")
        graph.remove_node(n)

    logger.info(
        f"Graph built: {graph.number_of_nodes()} nodes, "
        f"{graph.number_of_edges()} edges."
    )
    return graph


def get_node_depths(graph: nx.DiGraph) -> dict[str, int]:
    """Return a mapping of DOI -> depth from the graph node attributes."""
    return {n: graph.nodes[n].get("depth", 0) for n in graph.nodes}
