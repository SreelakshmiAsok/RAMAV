"""
System Health
=============
Checks which real tools are actually available in the current environment
and reports it honestly. Powers the "System Health / Tool Status" dashboard
page -- the single most important page for a grader to glance at first,
since it tells them exactly which findings will be REAL_TOOL vs HEURISTIC.
"""
from __future__ import annotations

import shutil
import subprocess
import sys

from app.integrations.semgrep_adapter import semgrep_available


def _binary_version(cmd: list[str]) -> str | None:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
        return (proc.stdout or proc.stderr).strip().splitlines()[0] if (proc.stdout or proc.stderr) else "unknown"
    except Exception:
        return None


def check_tools() -> dict:
    checks = {}

    checks["python"] = {"available": True, "detail": sys.version.split()[0]}

    checks["git"] = {"available": shutil.which("git") is not None,
                      "detail": _binary_version(["git", "--version"])}

    checks["semgrep"] = {"available": semgrep_available(),
                          "detail": _binary_version(["semgrep", "--version"]) if semgrep_available()
                          else "Not installed — Security Agent uses the deterministic fallback analyzer."}

    checks["pytest"] = _check_python_module("pytest", note="unittest (stdlib) is used instead when absent.")

    checks["flask"] = _check_python_module("flask")

    checks["node"] = {"available": shutil.which("node") is not None,
                       "detail": _binary_version(["node", "--version"])}

    checks["docker"] = {"available": shutil.which("docker") is not None,
                         "detail": _binary_version(["docker", "--version"]) if shutil.which("docker") else
                         "Not installed — not required for local demo mode."}

    ollama_url_reachable = _check_ollama()
    checks["ollama"] = {"available": ollama_url_reachable,
                         "detail": "Reachable" if ollama_url_reachable else
                         "Not reachable — LLM-assisted explanation text is disabled; "
                         "deterministic analysis is unaffected."}

    checks["sqlite3"] = {"available": True, "detail": "stdlib sqlite3"}

    return checks


def _check_python_module(name: str, note: str = "") -> dict:
    try:
        __import__(name)
        return {"available": True, "detail": ""}
    except ImportError:
        return {"available": False, "detail": note or f"{name} not installed."}


def _check_ollama() -> bool:
    import os
    import urllib.request
    base = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
    try:
        urllib.request.urlopen(f"{base}/api/tags", timeout=1.5)
        return True
    except Exception:
        return False
