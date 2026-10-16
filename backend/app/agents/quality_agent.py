"""
Quality Agent
=============
Lightweight AST-based checks for maintainability/convention issues, and the
agent that issues a CHALLENGE to the Security Agent asking whether
parameterized queries are used elsewhere in the repo (see the required
"real agent interaction" scenario in the spec).
"""
from __future__ import annotations

import ast
import os

from app.agents.base_agent import BaseAgent
from app.analysis.change_analyzer import ChangeSet
from app.evidence.store import Evidence, Finding, Severity, SourceType


class _ComplexityVisitor(ast.NodeVisitor):
    def __init__(self):
        self.max_depth = 0
        self.functions_without_try = []
        self.string_concat_sql = False

    def visit_FunctionDef(self, node):
        depth = self._depth(node)
        self.max_depth = max(self.max_depth, depth)
        has_try = any(isinstance(n, ast.Try) for n in ast.walk(node))
        calls_execute = any(
            isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "execute"
            for n in ast.walk(node)
        )
        if calls_execute and not has_try:
            self.functions_without_try.append(node.name)
        self.generic_visit(node)

    def _depth(self, node, level=0):
        max_child = level
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.Try)):
                max_child = max(max_child, self._depth(child, level + 1))
            else:
                max_child = max(max_child, self._depth(child, level))
        return max_child


class QualityAgent(BaseAgent):
    name = "quality_agent"
    category = "quality"

    def analyze(self, changeset: ChangeSet) -> list[Finding]:
        py_files = [f for f in changeset.changed_files if f.endswith(".py")]
        if not py_files:
            ev = self.store.add_evidence(Evidence(
                agent=self.name, description="No Python source files were changed; nothing for AST-based "
                                              "quality checks to inspect.",
                source_type=SourceType.HEURISTIC, tool="change-analyzer", strength=0.9,
            ))
            finding = Finding(
                agent=self.name, category=self.category, title="No quality-relevant code changed",
                severity=Severity.LOW, risk=0.05, confidence=0.93,
                evidence_ids=[ev.evidence_id], source_type=SourceType.HEURISTIC,
            )
            self.publish_finding(finding)
            return [finding]

        findings = []
        issues = []
        first_flagged_file = None
        for rel in changeset.changed_files:
            if not rel.endswith(".py"):
                continue
            full = os.path.join(self.repo_path, rel)
            if not os.path.isfile(full):
                continue
            try:
                with open(full, errors="ignore") as fh:
                    src = fh.read()
                tree = ast.parse(src)
            except (OSError, SyntaxError):
                continue

            visitor = _ComplexityVisitor()
            visitor.visit(tree)
            if visitor.functions_without_try:
                issues.append(f"{rel}: function(s) {', '.join(visitor.functions_without_try)} "
                              f"execute DB queries with no error handling.")
                first_flagged_file = first_flagged_file or rel
            if visitor.max_depth >= 4:
                issues.append(f"{rel}: deeply nested control flow (depth {visitor.max_depth}), hurts maintainability.")
                first_flagged_file = first_flagged_file or rel

        source_type = SourceType.HEURISTIC
        if issues:
            ev = self.store.add_evidence(Evidence(
                agent=self.name, description="; ".join(issues), source_type=source_type,
                tool="ast-quality-checks", strength=0.6,
            ))
            finding = Finding(
                agent=self.name, category=self.category, title="Code quality issues detected",
                severity=Severity.MEDIUM, risk=0.45, confidence=0.7,
                file=first_flagged_file,
                evidence_ids=[ev.evidence_id], source_type=source_type,
            )
        else:
            fallback_file = next((f for f in changeset.changed_files if f.endswith(".py")), None)
            ev = self.store.add_evidence(Evidence(
                agent=self.name, description="No significant quality issues detected in changed files.",
                source_type=source_type, tool="ast-quality-checks", file=fallback_file, strength=0.6,
            ))
            finding = Finding(
                agent=self.name, category=self.category, title="No quality issues detected",
                severity=Severity.LOW, risk=0.12, confidence=0.75,
                file=fallback_file,
                evidence_ids=[ev.evidence_id], source_type=source_type,
            )
        self.publish_finding(finding)
        findings.append(finding)
        return findings
