# Workspace

## Overview

pnpm workspace monorepo (TypeScript/Node.js) + standalone Python/Flask application for citation contamination analysis.

## Node.js Stack

- **Monorepo**: pnpm workspaces
- **Node**: 24, **TypeScript**: 5.9
- **API framework**: Express 5, **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod, **API codegen**: Orval

## Key Node.js Commands

- `pnpm run typecheck` — full typecheck
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks
- `pnpm --filter @workspace/db run push` — push DB schema (dev)
- `pnpm --filter @workspace/api-server run dev` — run API server

---

## Citation Contamination Intelligence System

**Location:** `citation-app/`
**Workflow:** "Citation Contamination System" → `cd citation-app && python flask_app.py` on port 5000
**Entry points:**
- Web UI: `python flask_app.py`
- CLI: `python main.py <DOI>`
- Data processing: `python process_data.py`

### Architecture

| File | Purpose |
|------|---------|
| `flask_app.py` | Flask web server — routes, job queue, templates |
| `main.py` | CLI pipeline entry point |
| `process_data.py` | CSV → processed_retractions.json (run once) |
| `modules/doi_validator.py` | DOI validation & normalization |
| `modules/retraction_detector.py` | O(1) lookup in processed_retractions.json |
| `modules/citation_fetcher.py` | OpenCitations API + disk cache |
| `modules/metadata_fetcher.py` | Semantic Scholar API + disk cache |
| `modules/cache.py` | Thread-safe disk-backed JSON cache (DiskCache) |
| `modules/graph_builder.py` | NetworkX directed graph, BFS, max 150 nodes/3 hops |
| `modules/risk_engine.py` | Risk formula + keyword classification + ranking |
| `modules/graph_viz.py` | PyVis interactive graph HTML |
| `modules/pipeline.py` | End-to-end orchestrator |
| `templates/` | Flask/Jinja2 HTML templates (base, index, waiting, results) |
| `data/retraction_watch.csv` | Raw Retraction Watch dataset (69,709 rows) |
| `data/processed_retractions.json` | Pre-processed index (60,936 DOIs, fast lookup) |
| `data/cache_citations.json` | OpenCitations API cache (7-day TTL) |
| `data/cache_metadata.json` | Semantic Scholar API cache (3-day TTL) |

### Risk Formula
```
depth_weight = {1: 1.0, 2: 0.5, 3: 0.2}
influence    = log(1 + citation_count)
risk_score   = depth_weight × influence
if retracted → risk_score × 2.0
```
High-risk keywords: "systematic review", "meta-analysis", "review"

### Data Sources (zero synthetic data)
- **OpenCitations COCI API** — citation edges
- **Semantic Scholar API** — title, abstract, authors, citation count, year
- **Retraction Watch** — retraction status (60,936 DOIs indexed)

### Pipeline Flow
```
DOI input → validate → retraction check (O1) → BFS citation graph
→ metadata enrichment → risk scoring → rank → render
```
