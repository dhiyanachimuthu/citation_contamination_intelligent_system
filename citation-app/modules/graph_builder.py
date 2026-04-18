"""
Graph builder — directed forward citation graph via BFS.
A → B means paper A cites paper B (A is contaminated by B).
Root node = input DOI. Hop 1 = papers citing root. Etc.
"""

import logging
from collections import deque
from typing import Callable
import networkx as nx

from .citation_fetcher import fetch_citing_dois

logger = logging.getLogger(__name__)

MAX_NODES = 150
MAX_HOPS  = 3


def _normalize_doi(doi: str) -> str:
    return doi.strip().lower()


def build_citation_graph(
    root_doi: str,
    max_nodes: int = MAX_NODES,
    max_hops:  int = MAX_HOPS,
    progress_cb: Callable[[str], None] | None = None,
) -> nx.DiGraph:
    """
    BFS citation graph starting from root_doi.
    Edges: citing_paper → cited_paper (citing cites cited).
    
    For contamination: at hop 1 we add papers that CITE root,
    showing they rely on the root paper's findings.
    """
    def step(msg: str):
        if progress_cb:
            progress_cb(msg)

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

        step(f"Fetching papers citing {current_doi[:30]}… (hop {depth+1}, {graph.number_of_nodes()} nodes so far)")
        citing_dois = fetch_citing_dois(current_doi)
        logger.info(f"Hop {depth+1} from {current_doi}: {len(citing_dois)} citing papers")

        for citing_doi in citing_dois:
            if graph.number_of_nodes() >= max_nodes:
                logger.info(f"Node cap ({max_nodes}) reached.")
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

            # Edge: citing paper → root paper (A cites B: A depends on B)
            if not graph.has_edge(norm, current_doi):
                graph.add_edge(norm, current_doi)

    # Remove any invalid nodes
    for n in [n for n in list(graph.nodes) if not str(n).startswith("10.")]:
        logger.warning(f"Removing invalid node: {n}")
        graph.remove_node(n)

    logger.info(f"Graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
    return graph


def get_node_depths(graph: nx.DiGraph) -> dict[str, int]:
    return {n: graph.nodes[n].get("depth", 0) for n in graph.nodes}
