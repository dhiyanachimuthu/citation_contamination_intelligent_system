"""
Citation Contamination Intelligence System
Flask Web Application — pure HTTP, no WebSockets required.
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


def _rw_status() -> dict:
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
        _jobs[job_id] = {
            "status": "queued",
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
    return jsonify({"status": job["status"]})


@app.route("/job/<job_id>/result")
def job_result(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job:
        return render_template("index.html", rw_status=_rw_status(), error="Job not found."), 404

    status = job["status"]

    if status == "error":
        return render_template(
            "index.html",
            rw_status=_rw_status(),
            error=f"Analysis failed: {job.get('error', 'Unknown error')}",
        )

    if status in ("queued", "running"):
        result_val = job.get("result")
        doi_val = result_val.get("root_doi", "") if result_val else ""
        return render_template("waiting.html", job_id=job_id, doi=doi_val)

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
        job_id=job_id,
        root_doi=root_doi,
        retraction=retraction,
        papers=papers,
        graph_html=graph_html,
        node_count=result.get("node_count", 0),
        edge_count=result.get("edge_count", 0),
        high_risk_count=high_risk_count,
        retracted_count=retracted_count,
    )


@app.route("/job/<job_id>/export")
def export_csv(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)

    if not job or job["status"] != "done":
        return "Not ready", 404

    papers = job["result"].get("papers", [])
    root_doi = job["result"].get("root_doi", "unknown")

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=[
        "doi", "title", "citation_count", "year",
        "depth_level", "risk_score", "risk_level",
        "is_retracted", "high_risk_keyword",
    ])
    writer.writeheader()
    for p in papers:
        writer.writerow({
            "doi": p.get("doi", ""),
            "title": p.get("title") or "NULL",
            "citation_count": p.get("citation_count") if p.get("citation_count") is not None else "NULL",
            "year": p.get("year") or "NULL",
            "depth_level": p.get("depth_level", ""),
            "risk_score": p.get("risk_score", ""),
            "risk_level": p.get("risk_level", ""),
            "is_retracted": p.get("is_retracted", False),
            "high_risk_keyword": p.get("high_risk_keyword", False),
        })

    safe_doi = root_doi.replace("/", "_")
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="citation_contamination_{safe_doi}.csv"'},
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info(f"Starting Flask app on 0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
