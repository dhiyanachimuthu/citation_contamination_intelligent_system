# Workspace

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.
Also contains a standalone Python/Streamlit application for citation contamination analysis.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)
- **Python**: 3.11 (for Streamlit app)

## Key Commands

- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- `pnpm --filter @workspace/api-server run dev` — run API server locally

See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details.

## Citation Contamination Intelligence System

Located in `citation-app/`. A Python/Streamlit application that detects how retracted scientific papers
propagate influence through real citation networks.

### Architecture

| File | Purpose |
|------|---------|
| `citation-app/app.py` | Main Streamlit dashboard |
| `citation-app/modules/doi_validator.py` | DOI validation & normalization |
| `citation-app/modules/retraction_detector.py` | Retraction Watch dataset lookup |
| `citation-app/modules/citation_fetcher.py` | OpenCitations API client |
| `citation-app/modules/metadata_fetcher.py` | Semantic Scholar API client |
| `citation-app/modules/graph_builder.py` | NetworkX directed citation graph |
| `citation-app/modules/risk_engine.py` | Risk score computation & ranking |
| `citation-app/modules/graph_viz.py` | PyVis interactive graph HTML |
| `citation-app/modules/pipeline.py` | End-to-end pipeline orchestrator |
| `citation-app/download_retraction_watch.py` | Helper to download RW dataset |
| `citation-app/data/retraction_watch.csv` | Local Retraction Watch CSV (required) |

### Data Sources (real data only — zero synthetic)
- **OpenCitations COCI API** — citation relationships
- **Semantic Scholar API** — paper metadata
- **Retraction Watch** — retraction status (local CSV at `citation-app/data/retraction_watch.csv`)

### Risk Formula
```
depth_weight = {1: 1.0, 2: 0.5, 3: 0.2}
influence = log(1 + citation_count)
risk_score = depth_weight × influence
if retracted: risk_score × 2.0
```

### Running
Workflow: "Citation Contamination System"
Command: `cd citation-app && streamlit run app.py --server.port 5000`
