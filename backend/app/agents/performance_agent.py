"""
Performance Agent
=================
Heuristic detection of obviously expensive patterns (nested loops touching
the DB, N+1 query shapes). We deliberately do NOT fabricate benchmark
numbers -- when a real timing benchmark cannot be run, the finding is
labeled HEURISTIC, never REAL_TOOL.
"""
from __future__ import annotations

import ast
import os

from app.agents.base_agent import BaseAgent
from app.analysis.change_analyzer import ChangeSet
from app.evidence.store import Evidence, Finding, Severity, SourceType


class _LoopDbVisitor(ast.NodeVisitor):
    def __init__(self):
        self.loop_with_db_call = False

    def visit_For(self, node):
        for n in ast.walk(node):
            if isinstance(n, ast.Call) and getattr(n.func, "attr", "") in ("execute", "query"):
                self.loop_with_db_call = True
        self.generic_visit(node)

    visit_While = visit_For


class PerformanceAgent(BaseAgent):
    name = "performance_agent"
    category = "performance"

    def analyze(self, changeset: ChangeSet) -> list[Finding]:
        findings = []
        flagged_files = []
        for rel in changeset.changed_files:
            if not rel.endswith(".py"):
                continue
            full = os.path.join(self.repo_path, rel)
            if not os.path.isfile(full):
                continue
            try:
                with open(full, errors="ignore") as fh:
                    tree = ast.parse(fh.read())
            except (OSError, SyntaxError):
                continue
            v = _LoopDbVisitor()
            v.visit(tree)
            if v.loop_with_db_call:
                flagged_files.append(rel)

        source_type = SourceType.HEURISTIC
        if flagged_files:
            ev = self.store.add_evidence(Evidence(
                agent=self.name,
                description=f"Possible N+1 query pattern (DB call inside a loop) in: {', '.join(flagged_files)}. "
                            f"No real benchmark was run; this is a static heuristic.",
                source_type=source_type, tool="ast-loop-heuristic", strength=0.5,
            ))
            finding = Finding(
                agent=self.name, category=self.category, title="Possible N+1 query pattern",
                severity=Severity.LOW, risk=0.3, confidence=0.55,
                evidence_ids=[ev.evidence_id], source_type=source_type,
            )
        else:
            ev = self.store.add_evidence(Evidence(
                agent=self.name, description="No obviously expensive loop/DB patterns detected.",
                source_type=source_type, tool="ast-loop-heuristic", strength=0.6,
            ))
            finding = Finding(
                agent=self.name, category=self.category, title="No performance concerns detected",
                severity=Severity.INFO, risk=0.05, confidence=0.7,
                evidence_ids=[ev.evidence_id], source_type=source_type,
            )
        self.publish_finding(finding)
        findings.append(finding)
        return findings
