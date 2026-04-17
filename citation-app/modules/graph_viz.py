"""
Graph visualization module using PyVis / NetworkX.
Returns HTML string for embedding in Streamlit.
"""

import tempfile
import os
import logging
import networkx as nx

logger = logging.getLogger(__name__)

try:
    from pyvis.network import Network
    PYVIS_AVAILABLE = True
except ImportError:
    PYVIS_AVAILABLE = False
    logger.warning("PyVis not available. Graph visualization will be limited.")

NODE_COLORS = {
    "retracted": "#E53E3E",
    "HIGH": "#ED8936",
    "MEDIUM": "#ECC94B",
    "LOW": "#48BB78",
    "root": "#3182CE",
}


def _get_node_color(doi: str, root_doi: str, papers_map: dict) -> str:
    if doi == root_doi:
        paper = papers_map.get(doi)
        if paper and paper.get("is_retracted"):
            return NODE_COLORS["retracted"]
        return NODE_COLORS["root"]

    paper = papers_map.get(doi)
    if not paper:
        return NODE_COLORS["LOW"]

    if paper.get("is_retracted"):
        return NODE_COLORS["retracted"]

    risk_level = paper.get("risk_level", "LOW")
    return NODE_COLORS.get(risk_level, NODE_COLORS["LOW"])


def build_pyvis_html(
    graph: nx.DiGraph,
    root_doi: str,
    papers: list[dict],
    height: str = "600px",
) -> str | None:
    """
    Generate PyVis HTML for the citation graph.
    Returns HTML string or None if PyVis unavailable or no nodes.
    """
    if not PYVIS_AVAILABLE:
        return None

    if graph.number_of_nodes() == 0:
        return None

    papers_map = {p["doi"]: p for p in papers}

    net = Network(
        height=height,
        width="100%",
        directed=True,
        bgcolor="#1a202c",
        font_color="#e2e8f0",
    )
    net.set_options("""
    {
      "physics": {
        "enabled": true,
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {
          "gravitationalConstant": -50,
          "springLength": 120,
          "springConstant": 0.08
        },
        "stabilization": {
          "iterations": 100
        }
      },
      "nodes": {
        "shape": "dot",
        "size": 16,
        "font": {"size": 11, "color": "#e2e8f0"}
      },
      "edges": {
        "arrows": "to",
        "color": {"color": "#4a5568", "opacity": 0.7},
        "smooth": {"type": "continuous"}
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 100
      }
    }
    """)

    for node in graph.nodes:
        color = _get_node_color(node, root_doi, papers_map)
        paper = papers_map.get(node)
        title_text = paper.get("title") if paper else None
        label = node[:20] + "..." if len(node) > 20 else node
        tooltip = f"DOI: {node}"
        if title_text:
            tooltip += f"\nTitle: {title_text[:80]}"
        if paper:
            tooltip += f"\nRisk: {paper.get('risk_level', 'N/A')}"
            tooltip += f"\nCitations: {paper.get('citation_count', 'N/A')}"
            if paper.get("is_retracted"):
                tooltip += "\n⚠ RETRACTED"

        size = 20 if node == root_doi else 14
        net.add_node(
            node,
            label=label,
            color=color,
            title=tooltip,
            size=size,
        )

    for src, dst in graph.edges:
        net.add_edge(src, dst)

    try:
        with tempfile.NamedTemporaryFile(
            suffix=".html", delete=False, mode="w", encoding="utf-8"
        ) as f:
            tmp_path = f.name

        net.save_graph(tmp_path)

        with open(tmp_path, encoding="utf-8") as f:
            html = f.read()

        os.unlink(tmp_path)
        return html
    except Exception as e:
        logger.error(f"PyVis graph generation failed: {e}")
        return None
