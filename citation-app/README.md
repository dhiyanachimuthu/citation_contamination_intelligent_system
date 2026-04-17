# Citation Contamination Intelligence System

Detects how retracted scientific papers propagate influence through real citation networks.

## Data Sources

- **OpenCitations COCI API** — real citation relationships
- **Semantic Scholar API** — paper metadata (title, abstract, citation count, year)
- **Retraction Watch dataset** — retraction status (local CSV)

## Zero Hallucination Policy

- No synthetic data, no placeholder nodes, no fake DOIs
- Missing fields are NULL — never approximated
- API failures return empty results, not fallbacks

## Setup

### 1. Install dependencies

```bash
pip install streamlit requests networkx pandas pyvis thefuzz python-Levenshtein plotly
```

### 2. Get the Retraction Watch dataset

Download the CSV from https://retractionwatch.com/retraction-watch-database-user-guide/
and place it at `data/retraction_watch.csv`.

Or try the download helper (requires API access):
```bash
python download_retraction_watch.py
```

### 3. Run the app

```bash
streamlit run app.py --server.port 5000
```

## Architecture

| Module | Responsibility |
|--------|---------------|
| `modules/doi_validator.py` | DOI format validation and normalization |
| `modules/retraction_detector.py` | Retraction Watch dataset lookup |
| `modules/citation_fetcher.py` | OpenCitations API client |
| `modules/metadata_fetcher.py` | Semantic Scholar API client |
| `modules/graph_builder.py` | NetworkX directed citation graph |
| `modules/risk_engine.py` | Risk score computation and ranking |
| `modules/graph_viz.py` | PyVis interactive graph HTML |
| `modules/pipeline.py` | End-to-end analysis orchestrator |
| `app.py` | Streamlit dashboard |

## Risk Score Formula

```
depth_weight = {1: 1.0, 2: 0.5, 3: 0.2}
influence = log(1 + citation_count)
risk_score = depth_weight × influence
if retracted: risk_score × 2.0
```

High-risk classification: title/abstract contains "systematic review", "meta-analysis", or "review"
