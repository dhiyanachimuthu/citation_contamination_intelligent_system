"""
Graph visualization module using PyVis / NetworkX.
Node size is proportional to risk score.
Colors: Blue=root, Red=HIGH/RETRACTED, Orange=MEDIUM, Blue-light=LOW, Green=SAFE
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
    logger.warning("PyVis not available.")

# Color palette matching UI CSS vars
NODE_COLORS = {
    "root":      "#3182CE",   # Blue — root paper
    "RETRACTED": "#E53E3E",   # Red
    "HIGH":      "#ED8936",   # Orange
    "MEDIUM":    "#ECC94B",   # Yellow
    "LOW":       "#4a9eff",   # Light blue
    "SAFE":      "#48BB78",   # Green
    "unknown":   "#718096",   # Grey fallback
}

ROOT_BORDER  = "#90CDF4"   # Light blue border for root node


def _node_size(risk_score: float, is_root: bool) -> int:
    """Node size proportional to risk score. Root is always large."""
    if is_root:
        return 32
    if risk_score is None or risk_score == 0:
        return 10
    # Scale: 0→10px, 1→14px, 3→20px, 10→32px (capped at 36)
    size = int(10 + risk_score * 3.5)
    return max(10, min(36, size))


def _node_color(doi: str, root_doi: str, papers_map: dict) -> str:
    if doi == root_doi:
        return NODE_COLORS["root"]
    p = papers_map.get(doi)
    if not p:
        return NODE_COLORS["unknown"]
    if p.get("is_retracted"):
        return NODE_COLORS["RETRACTED"]
    return NODE_COLORS.get(p.get("risk_level", "unknown"), NODE_COLORS["unknown"])


def _node_border(doi: str, root_doi: str) -> str:
    return ROOT_BORDER if doi == root_doi else "#2d3250"


def build_pyvis_html(
    graph: nx.DiGraph,
    root_doi: str,
    papers: list[dict],
    height: str = "600px",
) -> str | None:
    if not PYVIS_AVAILABLE or graph.number_of_nodes() == 0:
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
          "gravitationalConstant": -60,
          "springLength": 130,
          "springConstant": 0.06,
          "damping": 0.9
        },
        "stabilization": { "iterations": 150 }
      },
      "nodes": {
        "shape": "dot",
        "font": { "size": 10, "color": "#e2e8f0" },
        "borderWidth": 2,
        "shadow": true
      },
      "edges": {
        "arrows": { "to": { "enabled": true, "scaleFactor": 0.6 } },
        "color": { "color": "#4a5568", "opacity": 0.6 },
        "smooth": { "type": "continuous" },
        "width": 1.2
      },
      "interaction": {
        "hover": true,
        "tooltipDelay": 80,
        "navigationButtons": true,
        "keyboard": true
      }
    }
    """)

    for node in graph.nodes:
        p         = papers_map.get(node)
        color     = _node_color(node, root_doi, papers_map)
        border    = _node_border(node, root_doi)
        risk_s    = p.get("risk_score") if p else 0.0
        is_root   = (node == root_doi)
        size      = _node_size(risk_s or 0, is_root)
        label_str = node[:18] + "…" if len(node) > 18 else node

        # Build tooltip HTML
        parts = [f"<b>{node}</b>"]
        if p:
            if p.get("title"):
                parts.append(f"<i>{p['title'][:70]}{'…' if len(p.get('title',''))>70 else ''}</i>")
            parts.append(f"Risk: {p.get('risk_level','N/A')}  Score: {p.get('risk_score',0):.3f}")
            parts.append(f"Sentiment: {p.get('sentiment','N/A')}")
            if p.get("citation_count") is not None:
                parts.append(f"Citations: {p['citation_count']}")
            if p.get("year"):
                parts.append(f"Year: {p['year']}")
            if p.get("is_retracted"):
                parts.append("⚠ RETRACTED")
        if is_root:
            parts.insert(1, "★ ROOT PAPER")
        tooltip = "<br>".join(parts)

        net.add_node(
            node,
            label=label_str,
            color={"background": color, "border": border, "highlight": {"background": color, "border": "#fff"}},
            title=tooltip,
            size=size,
        )

    for src, dst in graph.edges:
        net.add_edge(src, dst, color={"color": "#4a5568"})

    try:
        with tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w", encoding="utf-8") as f:
            tmp_path = f.name
        net.save_graph(tmp_path)
        with open(tmp_path, encoding="utf-8") as f:
            html = f.read()
        os.unlink(tmp_path)
        return html
    except Exception as e:
        logger.error(f"PyVis graph generation failed: {e}")
        return None
