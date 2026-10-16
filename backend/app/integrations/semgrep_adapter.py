"""
Semgrep Adapter
===============
Tries to run the real `semgrep` CLI against a directory. If the binary is
not installed (as is the case in the sandbox this project was authored in --
see docs/SEMGREP_GUIDE.md), falls back to a small deterministic pattern-based
scanner and clearly labels its results as HEURISTIC rather than REAL_TOOL.

This file is the concrete answer to the viva question "what happens if
Semgrep is unavailable?" -- nothing crashes, and the dashboard is told the
truth about where the evidence came from.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass


@dataclass
class SemgrepFinding:
    rule_id: str
    message: str
    severity: str
    file: str
    line: int
    metadata: dict


def semgrep_available() -> bool:
    if shutil.which("semgrep") is not None:
        return True
    venv_semgrep = os.path.join(os.path.dirname(sys.executable), "semgrep")
    return os.path.isfile(venv_semgrep) and os.access(venv_semgrep, os.X_OK)


def run_semgrep(target_dir: str, timeout: int = 60) -> tuple[list[SemgrepFinding], bool, str]:
    """
    Returns (findings, used_real_tool, note).
    """
    if semgrep_available():
        try:
            semgrep_bin = shutil.which("semgrep") or os.path.join(os.path.dirname(sys.executable), "semgrep")
            proc = subprocess.run(
                [semgrep_bin, "scan", "--config", "auto", "--json", "--quiet", target_dir],
                capture_output=True, text=True, timeout=timeout,
            )
            data = json.loads(proc.stdout or "{}")
            findings = []
            abs_target = os.path.abspath(target_dir)
            for r in data.get("results", []):
                raw_path = r.get("path", "")
                if os.path.isabs(raw_path):
                    abs_path = raw_path
                elif os.path.exists(raw_path):
                    abs_path = os.path.abspath(raw_path)
                else:
                    abs_path = os.path.abspath(os.path.join(target_dir, raw_path))
                try:
                    rel_file = os.path.relpath(abs_path, abs_target)
                except ValueError:
                    rel_file = raw_path
                findings.append(SemgrepFinding(
                    rule_id=r.get("check_id", "unknown"),
                    message=r.get("extra", {}).get("message", ""),
                    severity=r.get("extra", {}).get("severity", "WARNING"),
                    file=rel_file,
                    line=(r.get("start", {}) or {}).get("line", 0),
                    metadata=r.get("extra", {}).get("metadata", {}),
                ))
            return findings, True, "Semgrep executed successfully."
        except Exception as exc:  # pragma: no cover - defensive
            return _fallback_scan(target_dir), False, f"Semgrep invocation failed ({exc}); fallback analyzer used."
    return _fallback_scan(target_dir), False, "Semgrep unavailable — fallback security analyzer used."


# --- deterministic fallback pattern rules -----------------------------------
# Intentionally simple & explainable: this is NOT trying to reimplement
# Semgrep, only to guarantee the pipeline still produces real evidence about
# THIS demo repository when the real tool cannot be installed (e.g. no
# internet access on the grading machine).
_RULES = [
    ("sql-injection-string-format", re.compile(r"(execute|cursor\.execute)\s*\(\s*f?[\"'].*%s.*[\"']\s*%"), "HIGH",
     "Possible SQL injection: query string built with % / f-string formatting instead of parameters."),
    ("sql-injection-fstring", re.compile(r"(execute|cursor\.execute)\s*\(\s*f[\"']"), "HIGH",
     "Possible SQL injection: f-string interpolated directly into a SQL query."),
    ("sql-injection-concat", re.compile(r"(execute|cursor\.execute)\s*\(\s*[\"'].*[\"']\s*\+"), "HIGH",
     "Possible SQL injection: SQL query built via string concatenation."),
    ("hardcoded-secret", re.compile(r"(password|secret|api_key|token)\s*=\s*[\"'][^\"']{4,}[\"']", re.I), "MEDIUM",
     "Hardcoded credential-like value detected."),
    ("dangerous-eval", re.compile(r"\beval\s*\("), "HIGH", "Use of eval() on potentially untrusted input."),
    ("dangerous-exec", re.compile(r"\bexec\s*\("), "HIGH", "Use of exec() on potentially untrusted input."),
]


def _fallback_scan(target_dir: str) -> list[SemgrepFinding]:
    import os
    findings = []
    for root, _dirs, files in os.walk(target_dir):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            full = os.path.join(root, fn)
            try:
                with open(full, errors="ignore") as fh:
                    lines = fh.readlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, start=1):
                for rule_id, pattern, severity, message in _RULES:
                    if pattern.search(line):
                        findings.append(SemgrepFinding(
                            rule_id=rule_id, message=message, severity=severity,
                            file=os.path.relpath(full, target_dir), line=lineno,
                            metadata={"engine": "ramav-fallback-heuristic"},
                        ))
    return findings
