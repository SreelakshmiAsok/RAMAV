"""
Database layer
==============
Uses plain stdlib sqlite3 rather than SQLAlchemy (no network access to
install it in the environment this project was authored in -- see
docs/ENVIRONMENT_NOTES.md). The schema below mirrors the model list from the
spec (AnalysisRun, Finding, Evidence, AgentMessage, Decision, ...) using
JSON columns for nested structures, which keeps this file small while still
persisting the complete analysis history for the "Analysis Replay" feature
and the History page.

Swapping this for SQLAlchemy models later is mechanical: the table shapes
below map directly onto ORM models with the same column names.
"""
from __future__ import annotations

import json
import os
import sqlite3
import time
from contextlib import contextmanager

DB_PATH = os.environ.get("RAMAV_DB_PATH", os.path.join(os.path.dirname(__file__), "..", "..", "ramav.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_runs (
    id TEXT PRIMARY KEY,
    pr_id TEXT NOT NULL,
    scenario TEXT,
    created_at REAL NOT NULL,
    duration_seconds REAL,
    decision_outcome TEXT,
    risk REAL,
    confidence REAL,
    result_json TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tool_status_cache (
    tool_name TEXT PRIMARY KEY,
    available INTEGER NOT NULL,
    detail TEXT,
    checked_at REAL NOT NULL
);
"""


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db():
    with get_conn() as conn:
        conn.executescript(SCHEMA)


def save_analysis_run(run_id: str, pr_id: str, scenario: str, result: dict):
    with get_conn() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO analysis_runs
               (id, pr_id, scenario, created_at, duration_seconds, decision_outcome, risk, confidence, result_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run_id, pr_id, scenario, time.time(),
                result.get("duration_seconds"),
                result.get("decision", {}).get("outcome"),
                result.get("decision", {}).get("risk"),
                result.get("decision", {}).get("confidence"),
                json.dumps(result),
            ),
        )


def get_analysis_run(run_id: str) -> dict | None:
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM analysis_runs WHERE id = ?", (run_id,)).fetchone()
        if not row:
            return None
        d = dict(row)
        d["result"] = json.loads(d.pop("result_json"))
        return d


def list_analysis_runs(limit: int = 50) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT id, pr_id, scenario, created_at, duration_seconds, decision_outcome, risk, confidence "
            "FROM analysis_runs ORDER BY created_at DESC LIMIT ?", (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def cache_tool_status(tool_name: str, available: bool, detail: str = ""):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO tool_status_cache (tool_name, available, detail, checked_at) VALUES (?, ?, ?, ?)",
            (tool_name, int(available), detail, time.time()),
        )
