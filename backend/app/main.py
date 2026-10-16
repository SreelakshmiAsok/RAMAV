"""
RAMAV API (Flask)
==================
NOTE ON FRAMEWORK CHOICE: the project brief specifies FastAPI. This backend
uses Flask instead because the build environment this project was authored
in has no network access to `pip install fastapi/uvicorn/pydantic`, while
Flask happened to be pre-installed. The route shapes, JSON contracts and
status codes below are written so that porting to FastAPI is a mechanical,
low-risk change (see docs/TOOL_SELECTION.md, "Flask vs FastAPI"). No FastAPI version is
included; it was not built or tested.

All heavy lifting (agents, orchestrator, engines) lives in app/*, this file
only adapts it to HTTP.
"""
from __future__ import annotations

import os
import time
import uuid

from flask import Flask, jsonify, request, send_from_directory

from app.agents.orchestrator import Orchestrator
from app.analysis.change_analyzer import ChangeAnalyzer
from app.config.settings import full_config
from app.database import db
from app.integrations.git_utils import commit_range_summary
from app.services.repair_service import run_repair_and_revalidate
from app.services.system_health import check_tools

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SCENARIOS_DIR = os.path.join(REPO_ROOT, "demo-repository", "scenarios")
FRONTEND_DIR = os.path.join(REPO_ROOT, "frontend")

app = Flask(__name__)


@app.after_request
def add_cors_headers(response):
    # Hand-rolled instead of the flask-cors package (not installed in the
    # build sandbox / no network to install it) -- only matters if the
    # frontend is ever served from a different origin than the API.
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return response

db.init_db()

_RUN_CACHE: dict[str, dict] = {}


def _run_scenario(scenario: str, pr_id: str = None) -> dict:
    path = os.path.join(SCENARIOS_DIR, scenario)
    if not os.path.isdir(path):
        return {"error": f"Unknown scenario '{scenario}'"}
    pr_id = pr_id or f"PR-{scenario}-{int(time.time())}"
    orch = Orchestrator(path, pr_id)
    result = orch.run()
    result["scenario"] = scenario
    result["git"] = commit_range_summary(path)
    run_id = str(uuid.uuid4())
    result["run_id"] = run_id
    _RUN_CACHE[run_id] = result
    db.save_analysis_run(run_id, pr_id, scenario, result)
    return result


# ---------------------------------------------------------------------------
# Health / system
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "time": time.time()})


@app.get("/api/system/tools")
def system_tools():
    return jsonify(check_tools())


@app.get("/api/system/config")
def system_config():
    return jsonify(full_config())


@app.get("/api/system/peas")
def peas():
    # Static content, but served from the API (rather than hardcoded in the
    # frontend) so docs/dashboard/report all read from one source of truth.
    import json
    peas_path = os.path.join(REPO_ROOT, "docs", "peas.json")
    with open(peas_path) as fh:
        return jsonify(json.load(fh))


# ---------------------------------------------------------------------------
# Demo scenarios
# ---------------------------------------------------------------------------
@app.post("/api/demo/safe")
def demo_safe():
    return jsonify(_run_scenario("safe"))


@app.post("/api/demo/security")
def demo_security():
    return jsonify(_run_scenario("sql_injection"))


@app.post("/api/demo/disagreement")
def demo_disagreement():
    return jsonify(_run_scenario("disagreement"))


@app.post("/api/demo/low_evidence")
def demo_low_evidence():
    return jsonify(_run_scenario("low_evidence"))


@app.post("/api/demo/repair")
def demo_repair():
    result = run_repair_and_revalidate(os.path.join(SCENARIOS_DIR, "repair"), "PR-repair")
    run_id = str(uuid.uuid4())
    result["run_id"] = run_id
    result["scenario"] = "repair"
    _RUN_CACHE[run_id] = result
    db.save_analysis_run(run_id, "PR-repair", "repair", result.get("post_repair") or result.get("pre_repair"))
    return jsonify(result)


# ---------------------------------------------------------------------------
# Generic repository / PR analysis (works on any local directory, not just
# the bundled demo scenarios)
# ---------------------------------------------------------------------------
@app.post("/api/analyze/repository")
def analyze_repository():
    body = request.get_json(force=True, silent=True) or {}
    path = body.get("path")
    pr_id = body.get("pr_id", "local-pr")
    if not path or not os.path.isdir(path):
        return jsonify({"error": "Provide a valid local 'path' to a git repository."}), 400
    orch = Orchestrator(path, pr_id)
    result = orch.run()
    result["scenario"] = "custom"
    result["git"] = commit_range_summary(path)
    run_id = str(uuid.uuid4())
    result["run_id"] = run_id
    _RUN_CACHE[run_id] = result
    db.save_analysis_run(run_id, pr_id, "custom", result)
    return jsonify(result)


@app.post("/api/analyze/pr")
def analyze_pr():
    """GitHub PR analysis. Requires the repo to already be cloned locally
    (this local-demo build does not fetch from GitHub over the network)."""
    body = request.get_json(force=True, silent=True) or {}
    local_path = body.get("local_clone_path")
    pr_number = body.get("pr_number", "unknown")
    if not local_path or not os.path.isdir(local_path):
        return jsonify({
            "error": "GitHub integration in this build expects a 'local_clone_path' to an already-cloned "
                     "repository (no outbound network access in the build/grading sandbox). "
                     "See docs/ARCHITECTURE.md, 'GitHub integration'."
        }), 400
    orch = Orchestrator(local_path, f"PR-{pr_number}")
    result = orch.run()
    return jsonify(result)


# ---------------------------------------------------------------------------
# Analysis retrieval
# ---------------------------------------------------------------------------
def _get_run(run_id: str) -> dict | None:
    if run_id in _RUN_CACHE:
        return _RUN_CACHE[run_id]
    row = db.get_analysis_run(run_id)
    return row["result"] if row else None


@app.get("/api/analysis/<run_id>")
def get_analysis(run_id):
    result = _get_run(run_id)
    if result is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(result)


@app.get("/api/analysis/<run_id>/messages")
def get_messages(run_id):
    result = _get_run(run_id)
    if result is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(result.get("messages", []))


@app.get("/api/analysis/<run_id>/findings")
def get_findings(run_id):
    result = _get_run(run_id)
    if result is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(result.get("findings", []))


@app.get("/api/analysis/<run_id>/evidence")
def get_evidence(run_id):
    result = _get_run(run_id)
    if result is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(result.get("evidence", []))


@app.get("/api/analysis/<run_id>/decision")
def get_decision(run_id):
    result = _get_run(run_id)
    if result is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(result.get("decision", {}))


@app.get("/api/analysis/<run_id>/state")
def get_state(run_id):
    result = _get_run(run_id)
    if result is None:
        return jsonify({"error": "not found"}), 404
    return jsonify(result.get("state", {}))


@app.get("/api/history")
def history():
    return jsonify(db.list_analysis_runs())


# ---------------------------------------------------------------------------
# Serve the (no-build) frontend dashboard from the same origin, so the demo
# is a single `python3 main.py` + open-browser experience.
# ---------------------------------------------------------------------------
@app.get("/")
@app.get("/<path:path>")
def serve_frontend(path: str = "index.html"):
    full = os.path.join(FRONTEND_DIR, path)
    if not os.path.isfile(full):
        path = "index.html"
    return send_from_directory(FRONTEND_DIR, path)


if __name__ == "__main__":
    port = int(os.environ.get("RAMAV_PORT", "8000"))
    app.run(host="0.0.0.0", port=port, debug=False)
