"""
Citation Contamination Intelligence System
Streamlit Dashboard — real data only, no synthetic content.
"""

import os
import sys
import logging
import streamlit as st
import pandas as pd

sys.path.insert(0, os.path.dirname(__file__))

from modules.doi_validator import validate_doi
from modules.pipeline import run_analysis
from modules.graph_viz import build_pyvis_html

logging.basicConfig(level=logging.INFO)

st.set_page_config(
    page_title="Citation Contamination Intelligence System",
    page_icon="🔬",
    layout="wide",
)

st.title("Citation Contamination Intelligence System")
st.markdown(
    "Detect how retracted scientific papers propagate influence through real citation networks. "
    "All data sourced exclusively from **OpenCitations**, **Semantic Scholar**, and **Retraction Watch**."
)

with st.sidebar:
    st.header("About")
    st.info(
        "**Data Sources:**\n"
        "- OpenCitations API (citation graphs)\n"
        "- Semantic Scholar API (paper metadata)\n"
        "- Retraction Watch dataset (retraction status)\n\n"
        "**Rules:**\n"
        "- Zero synthetic data\n"
        "- Real DOIs only\n"
        "- NULL for missing fields\n"
        "- Max 150 nodes, 3-hop expansion"
    )
    st.markdown("---")
    st.subheader("Color Legend")
    st.markdown(
        "🔴 **Red** — Retracted paper\n\n"
        "🟠 **Orange** — High risk\n\n"
        "🟡 **Yellow** — Medium risk\n\n"
        "🟢 **Green** — Low risk\n\n"
        "🔵 **Blue** — Root paper"
    )

    st.markdown("---")
    st.subheader("Retraction Watch Dataset")
    rw_path = os.path.join(os.path.dirname(__file__), "data", "retraction_watch.csv")
    if os.path.exists(rw_path):
        size = os.path.getsize(rw_path)
        st.success(f"Dataset loaded ({size // 1024:,} KB)")
    else:
        st.warning(
            "Retraction Watch CSV not found locally.\n\n"
            "Download it from [Retraction Watch](https://retractionwatch.com/retraction-watch-database-user-guide/) "
            "and place it at `data/retraction_watch.csv`.\n\n"
            "Without it, retraction detection will not work."
        )

st.header("Paper Analysis")

col1, col2 = st.columns([3, 1])
with col1:
    doi_input = st.text_input(
        "Enter DOI",
        placeholder="e.g. 10.1038/nbt.3816",
        help="Accepts bare DOI, https://doi.org/ URLs, or doi: prefixed strings.",
    )

with col2:
    title_hint = st.text_input(
        "Paper Title (optional)",
        placeholder="Used as fallback if DOI missing from dataset",
        help="Only used for retraction detection fallback.",
    )

run_btn = st.button("Run Analysis", type="primary", use_container_width=True)

if run_btn:
    if not doi_input.strip():
        st.error("Please enter a DOI.")
        st.stop()

    is_valid, normalized = validate_doi(doi_input.strip())
    if not is_valid:
        st.error(
            f"**Invalid DOI format:** `{doi_input}`\n\n"
            "DOIs must match pattern: `10.XXXX/suffix` — e.g. `10.1038/nbt.3816`"
        )
        st.stop()

    st.info(f"Analyzing DOI: `{normalized}`")

    with st.spinner("Fetching citation network and metadata... This may take 30–120 seconds depending on citation volume."):
        result = run_analysis(doi_input.strip(), title_hint=title_hint.strip() or None)

    if not result["success"]:
        st.error(f"Analysis failed: {result['error']}")
        st.stop()

    retraction = result["retraction"]
    root_doi = result["root_doi"]
    graph = result["graph"]
    papers = result["papers"]

    st.markdown("---")
    st.header("Retraction Status")

    ret_col1, ret_col2, ret_col3 = st.columns(3)
    with ret_col1:
        if retraction["is_retracted"]:
            st.error("⚠ RETRACTED")
        else:
            st.success("✓ Not Retracted")

    with ret_col2:
        if retraction.get("reason"):
            st.metric("Retraction Reason", retraction["reason"][:60])
        else:
            st.metric("Retraction Reason", "N/A")

    with ret_col3:
        st.metric("Retraction Year", retraction.get("year") or "N/A")

    st.markdown("---")
    st.header("Citation Graph Statistics")

    stat_col1, stat_col2, stat_col3, stat_col4 = st.columns(4)
    with stat_col1:
        st.metric("Total Nodes", result["node_count"])
    with stat_col2:
        st.metric("Total Edges", result["edge_count"])
    with stat_col3:
        high_risk = sum(1 for p in papers if p.get("risk_level") == "HIGH")
        st.metric("High Risk Papers", high_risk)
    with stat_col4:
        retracted_count = sum(1 for p in papers if p.get("is_retracted"))
        st.metric("Retracted in Network", retracted_count)

    if graph.number_of_nodes() == 0:
        st.warning("No real citation data available from APIs for this DOI.")
    else:
        st.markdown("---")
        st.header("Citation Network Graph")

        graph_html = build_pyvis_html(graph, root_doi, papers)
        if graph_html:
            st.components.v1.html(graph_html, height=620, scrolling=False)
        else:
            st.info("Graph visualization unavailable. PyVis may not be installed.")

    st.markdown("---")
    st.header("Contamination Risk Rankings")

    if not papers:
        st.warning("No real citation data available from APIs.")
    else:
        table_rows = []
        for p in papers:
            table_rows.append({
                "DOI": p["doi"],
                "Title": p["title"] or "NULL",
                "Citation Count": p["citation_count"] if p["citation_count"] is not None else "NULL",
                "Year": p["year"] if p["year"] is not None else "NULL",
                "Depth Level": p["depth_level"],
                "Risk Score": p["risk_score"],
                "Risk Level": p["risk_level"],
                "Retracted": "⚠ YES" if p["is_retracted"] else "No",
                "High Risk Keywords": "Yes" if p["high_risk_keyword"] else "No",
            })

        df = pd.DataFrame(table_rows)

        def highlight_risk(row):
            level = row.get("Risk Level", "")
            retracted = row.get("Retracted", "")
            if retracted == "⚠ YES":
                return ["background-color: #fed7d7"] * len(row)
            elif level == "HIGH":
                return ["background-color: #feebc8"] * len(row)
            elif level == "MEDIUM":
                return ["background-color: #fefcbf"] * len(row)
            else:
                return ["background-color: #c6f6d5"] * len(row)

        styled_df = df.style.apply(highlight_risk, axis=1)
        st.dataframe(styled_df, use_container_width=True, height=500)

        st.download_button(
            label="Download Results as CSV",
            data=df.to_csv(index=False).encode("utf-8"),
            file_name=f"citation_contamination_{root_doi.replace('/', '_')}.csv",
            mime="text/csv",
        )

    with st.expander("Analysis Details & Methodology"):
        st.markdown(f"""
**Root DOI:** `{root_doi}`

**Risk Score Formula:**
- Depth 1 (direct citers): weight = 1.0
- Depth 2: weight = 0.5
- Depth 3: weight = 0.2
- Influence = log(1 + citation_count)
- risk_score = depth_weight × influence
- If retracted: risk_score × 2.0

**High Risk Classification:** Paper title/abstract contains "systematic review", "meta-analysis", or "review"

**Graph Limits:** Maximum 150 nodes, 3-hop expansion

**Data Sources:**
- Citation edges: OpenCitations COCI API
- Metadata (title, abstract, citationCount, year): Semantic Scholar API
- Retraction status: Retraction Watch dataset (local CSV)
        """)
