"""
Citation Contamination Intelligence System
Flask Web Application — pure HTTP, no WebSockets.
"""

import os
import sys
import csv
import io
import uuid
import logging
import threading

from flask import Flask, render_template, request, jsonify, Response

sys.path.insert(0, os.path.dirname(__file__))

from modules.doi_validator import validate_doi
from modules.pipeline import run_analysis
from modules.graph_viz import build_pyvis_html
from modules.cache import get_citations_cache, get_metadata_cache

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", "citation-contamination-dev-key")

_jobs: dict = {}
_jobs_lock = threading.Lock()


def _run_job(job_id: str, doi_input: str, title_hint: str | None):
    try:
        with _jobs_lock:
            _jobs[job_id]["status"] = "running"
            _jobs[job_id]["step"] = "Validating DOI and checking retraction status…"

        result = run_analysis(doi_input, title_hint=title_hint or None,
                              progress_cb=lambda msg: _set_step(job_id, msg))

        if result["success"]:
            _set_step(job_id, "Building graph visualization…")
            graph_html = build_pyvis_html(
                result["graph"],
                result["root_doi"],
                result["papers"],
            )
        else:
            graph_html = None

        with _jobs_lock:
            _jobs[job_id]["status"] = "done"
            _jobs[job_id]["result"] = result
            _jobs[job_id]["graph_html"] = graph_html

    except Exception as e:
        logger.exception(f"Job {job_id} failed: {e}")
        with _jobs_lock:
            _jobs[job_id]["status"] = "error"
            _jobs[job_id]["error"] = str(e)


def _set_step(job_id: str, msg: str):
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["step"] = msg


def _rw_status() -> dict:
    import json
    processed = os.path.join(os.path.dirname(__file__), "data", "processed_retractions.json")
    raw_csv   = os.path.join(os.path.dirname(__file__), "data", "retraction_watch.csv")
    if os.path.exists(processed):
        try:
            with open(processed) as f:
                data = json.load(f)
            stats = data.get("stats", {})
            return {
                "loaded": True,
                "source": "processed_retractions.json",
                "doi_count": stats.get("with_doi", 0),
                "total_rows": stats.get("total_rows", 0),
            }
        except Exception:
            pass
    if os.path.exists(raw_csv):
        size_kb = os.path.getsize(raw_csv) // 1024
        return {"loaded": True, "source": "retraction_watch.csv (raw)", "doi_count": 0, "total_rows": size_kb}
    return {"loaded": False}


def _cache_stats() -> dict:
    try:
        cc = get_citations_cache()
        mc = get_metadata_cache()
        return {"citations": cc.size(), "metadata": mc.size()}
    except Exception:
        return {"citations": 0, "metadata": 0}


# ── Health / proxy ────────────────────────────────────────────────────────────
@app.route("/_stcore/health")
@app.route("/healthz")
def health():
    return jsonify({"status": "ok"}), 200


@app.route("/_stcore/host-config")
def host_config():
    return jsonify({"allowedOrigins": ["*"], "useExternalAuthToken": False}), 200


# ── Main routes ───────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return render_template("index.html", rw_status=_rw_status(), cache_stats=_cache_stats())


@app.route("/analyze", methods=["POST"])
def analyze():
    doi_input  = (request.form.get("doi") or "").strip()
    title_hint = (request.form.get("title_hint") or "").strip()

    if not doi_input:
        return render_template("index.html", rw_status=_rw_status(),
                               cache_stats=_cache_stats(), error="Please enter a DOI.")

    is_valid, normalized = validate_doi(doi_input)
    if not is_valid:
        return render_template(
            "index.html",
            rw_status=_rw_status(),
            cache_stats=_cache_stats(),
            error=f"Invalid DOI format: '{doi_input}'. Format must be: 10.XXXX/suffix",
            doi_input=doi_input,
        )

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {
            "status": "queued",
            "step":   "Queued…",
            "result": None,
            "graph_html": None,
            "error": None,
        }

    thread = threading.Thread(
        target=_run_job,
        args=(job_id, doi_input, title_hint or None),
        daemon=True,
    )
    thread.start()

    return render_template("waiting.html", job_id=job_id, doi=normalized)


@app.route("/job/<job_id>/status")
def job_status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify({"status": job["status"], "step": job.get("step", "")})


@app.route("/job/<job_id>/graph")
def job_graph(job_id: str):
    """Serve the PyVis graph HTML directly — used as iframe src."""
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job or job["status"] != "done":
        return "Not ready", 404
    graph_html = job.get("graph_html")
    if not graph_html:
        return "<html><body style='background:#1a202c;color:#8892a4;font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;'>No citation data available from APIs for this DOI.</body></html>", 200
    return Response(graph_html, mimetype="text/html")


@app.route("/job/<job_id>/result")
def job_result(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return render_template("index.html", rw_status=_rw_status(),
                               cache_stats=_cache_stats(), error="Job not found."), 404

    status = job["status"]

    if status == "error":
        return render_template("index.html", rw_status=_rw_status(),
                               cache_stats=_cache_stats(),
                               error=f"Analysis failed: {job.get('error', 'Unknown error')}")

    if status in ("queued", "running"):
        doi_val = ""
        if job.get("result"):
            doi_val = job["result"].get("root_doi", "")
        return render_template("waiting.html", job_id=job_id, doi=doi_val)

    result        = job["result"]
    papers        = result.get("papers", [])
    retraction    = result.get("retraction", {})
    root_doi      = result.get("root_doi", "")
    analytics     = result.get("analytics", {})
    has_graph     = bool(job.get("graph_html"))

    return render_template(
        "results.html",
        rw_status=_rw_status(),
        cache_stats=_cache_stats(),
        job_id=job_id,
        root_doi=root_doi,
        retraction=retraction,
        papers=papers,
        has_graph=has_graph,
        node_count=result.get("node_count", 0),
        edge_count=result.get("edge_count", 0),
        analytics=analytics,
        high_risk_count=sum(1 for p in papers if p.get("risk_level") == "HIGH"),
        retracted_count=sum(1 for p in papers if p.get("is_retracted")),
    )


@app.route("/job/<job_id>/export")
def export_csv(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job or job["status"] != "done":
        return "Not ready", 404

    papers   = job["result"].get("papers", [])
    root_doi = job["result"].get("root_doi", "unknown")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "doi", "title", "authors", "year", "citation_count",
        "depth_level", "risk_score", "risk_level", "sentiment",
        "is_retracted", "high_risk_keyword",
    ])
    writer.writeheader()
    for p in papers:
        writer.writerow({
            "doi":               p.get("doi", ""),
            "title":             p.get("title") or "NULL",
            "authors":           "; ".join(p.get("authors") or []) or "NULL",
            "year":              p.get("year") or "NULL",
            "citation_count":    p.get("citation_count") if p.get("citation_count") is not None else "NULL",
            "depth_level":       p.get("depth_level", ""),
            "risk_score":        p.get("risk_score", ""),
            "risk_level":        p.get("risk_level", ""),
            "sentiment":         p.get("sentiment", "Neutral"),
            "is_retracted":      p.get("is_retracted", False),
            "high_risk_keyword": p.get("high_risk_keyword", False),
        })

    safe_doi = root_doi.replace("/", "_").replace(":", "_")
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="citation_contamination_{safe_doi}.csv"'},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting Flask on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
