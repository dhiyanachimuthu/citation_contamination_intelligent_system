"""
Citation Contamination Intelligence System
Flask Web Application — pure HTTP, no WebSockets.
"""

import os
import sys
import json
import uuid
import logging
import threading
from flask import Flask, render_template, request, jsonify, session

sys.path.insert(0, os.path.dirname(__file__))

from modules.doi_validator import validate_doi
from modules.pipeline import run_analysis
from modules.graph_viz import build_pyvis_html

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

        result = run_analysis(doi_input, title_hint=title_hint or None)

        if result["success"]:
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


def _rw_status():
    rw_path = os.path.join(os.path.dirname(__file__), "data", "retraction_watch.csv")
    if os.path.exists(rw_path):
        size_kb = os.path.getsize(rw_path) // 1024
        return {"loaded": True, "size_kb": size_kb}
    return {"loaded": False}


@app.route("/")
def index():
    return render_template("index.html", rw_status=_rw_status())


@app.route("/analyze", methods=["POST"])
def analyze():
    doi_input = (request.form.get("doi") or "").strip()
    title_hint = (request.form.get("title_hint") or "").strip()

    if not doi_input:
        return render_template("index.html", rw_status=_rw_status(), error="Please enter a DOI.")

    is_valid, normalized = validate_doi(doi_input)
    if not is_valid:
        return render_template(
            "index.html",
            rw_status=_rw_status(),
            error=f"Invalid DOI format: '{doi_input}'. DOIs must match: 10.XXXX/suffix",
            doi_input=doi_input,
        )

    job_id = str(uuid.uuid4())
    with _jobs_lock:
        _jobs[job_id] = {"status": "queued", "result": None, "graph_html": None, "error": None}

    thread = threading.Thread(target=_run_job, args=(job_id, doi_input, title_hint or None), daemon=True)
    thread.start()

    return render_template("waiting.html", job_id=job_id, doi=normalized)


@app.route("/job/<job_id>/status")
def job_status(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return jsonify({"status": "not_found"}), 404
    return jsonify({"status": job["status"]})


@app.route("/job/<job_id>/result")
def job_result(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        return "Job not found", 404

    status = job["status"]
    if status == "error":
        return render_template("index.html", rw_status=_rw_status(), error=f"Analysis failed: {job['error']}")

    if status != "done":
        return render_template("waiting.html", job_id=job_id, doi="")

    result = job["result"]
    graph_html = job["graph_html"]

    papers = result.get("papers", [])
    retraction = result.get("retraction", {})
    root_doi = result.get("root_doi", "")

    high_risk_count = sum(1 for p in papers if p.get("risk_level") == "HIGH")
    retracted_count = sum(1 for p in papers if p.get("is_retracted"))

    return render_template(
        "results.html",
        rw_status=_rw_status(),
        root_doi=root_doi,
        retraction=retraction,
        papers=papers,
        graph_html=graph_html,
        node_count=result.get("node_count", 0),
        edge_count=result.get("edge_count", 0),
        high_risk_count=high_risk_count,
        retracted_count=retracted_count,
    )


@app.route("/graph/<job_id>")
def graph_fullscreen(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job or job["status"] != "done":
        return "Graph not ready", 404
    graph_html = job.get("graph_html") or "<p>No graph data available.</p>"
    return graph_html


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
