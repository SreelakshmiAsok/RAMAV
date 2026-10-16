"""
Security Agent
===============
Runs Semgrep (or the deterministic fallback) plus a couple of simple AST/
regex heuristics, converts results into Findings + Evidence, and
participates in the conversation: it asks the Testing Agent for evidence
about whether malicious-input tests exist, and reassesses its own findings
when new evidence arrives.
"""
from __future__ import annotations

import os
import re

from app.agents.base_agent import BaseAgent
from app.analysis.change_analyzer import ChangeSet
from app.coordination.messages import AgentMessage, MessageType, Priority
from app.evidence.store import Evidence, Finding, Severity, SourceType
from app.integrations.semgrep_adapter import run_semgrep

SEVERITY_MAP = {
    "ERROR": Severity.HIGH, "WARNING": Severity.MEDIUM, "INFO": Severity.LOW,
    "HIGH": Severity.HIGH, "MEDIUM": Severity.MEDIUM, "LOW": Severity.LOW,
}

BASE_RISK = {Severity.CRITICAL: 0.95, Severity.HIGH: 0.80, Severity.MEDIUM: 0.55, Severity.LOW: 0.30, Severity.INFO: 0.1}


class SecurityAgent(BaseAgent):
    name = "security_agent"
    category = "security"

    def analyze(self, changeset: ChangeSet) -> list[Finding]:
        has_code = any(f.endswith(".py") for f in changeset.changed_files)
        if not has_code:
            ev = self.store.add_evidence(Evidence(
                agent=self.name, description="No source code files were changed in this PR; nothing for "
                                              "static security analysis to scan.",
                source_type=SourceType.HEURISTIC, tool="change-analyzer", strength=0.9,
            ))
            finding = Finding(
                agent=self.name, category=self.category, title="No security-relevant code changed",
                severity=Severity.LOW, risk=0.05, confidence=0.95,
                evidence_ids=[ev.evidence_id], source_type=SourceType.HEURISTIC,
            )
            self.publish_finding(finding)
            return [finding]

        findings: list[Finding] = []
        sg_findings, used_real_tool, note = run_semgrep(self.repo_path)
        source_type = SourceType.REAL_TOOL if used_real_tool else SourceType.HEURISTIC
        self.last_tool_note = note
        self.used_real_tool = used_real_tool

        for sf in sg_findings:
            severity = SEVERITY_MAP.get(sf.severity.upper(), Severity.MEDIUM)
            base_risk = BASE_RISK[severity]
            is_sqli = "sql" in sf.rule_id.lower() or "sql injection" in sf.message.lower()

            ev = self.store.add_evidence(Evidence(
                agent=self.name, description=sf.message, source_type=source_type,
                tool="semgrep" if used_real_tool else "ramav-fallback-heuristic",
                file=sf.file, line=sf.line, strength=0.9 if used_real_tool else 0.6,
            ))
            finding = Finding(
                agent=self.name, category=self.category,
                title=sf.message or sf.rule_id,
                severity=severity, risk=base_risk, confidence=0.82 if used_real_tool else 0.65,
                file=sf.file, line=sf.line,
                evidence_ids=[ev.evidence_id], source_type=source_type,
            )
            finding.payload_is_sqli = is_sqli  # informal tag used by orchestrator
            self.publish_finding(finding)
            findings.append(finding)

        if not sg_findings:
            primary_file = next((f for f in changeset.changed_files if f.endswith(".py")), None)
            ev = self.store.add_evidence(Evidence(
                agent=self.name, description="No security-relevant patterns detected in changed files.",
                source_type=source_type, tool="semgrep" if used_real_tool else "ramav-fallback-heuristic",
                file=primary_file, strength=0.7,
            ))
            finding = Finding(
                agent=self.name, category=self.category, title="No security issues detected",
                severity=Severity.LOW, risk=0.15, confidence=0.82,
                file=primary_file,
                evidence_ids=[ev.evidence_id], source_type=source_type,
            )
            self.publish_finding(finding)
            findings.append(finding)

        return findings

    def handle_message(self, message: AgentMessage):
        if message.type == MessageType.CHALLENGE and message.receiver == self.name:
            # "Does the SQL construction use parameterized queries elsewhere
            # in the repository?" -- answer with a real repository scan.
            uses_param_elsewhere = self._repo_uses_parameterized_queries()
            content = (
                "Yes, other modules in this repository use parameterized queries "
                "(e.g. execute(query, params)), which confirms the flagged file "
                "deviates from the project's established safe pattern."
                if uses_param_elsewhere else
                "No, parameterized queries are not consistently used elsewhere in "
                "this repository either; this appears to be a systemic pattern, not "
                "an isolated mistake."
            )
            return self.respond(message.sender, content, related_finding_id=message.related_finding_id)
        return None

    def _repo_uses_parameterized_queries(self) -> bool:
        pattern = re.compile(r"execute\s*\(\s*[\"'][^\"']*\?[^\"']*[\"']\s*,")
        alt = re.compile(r"execute\s*\(\s*[\"'][^\"']*%s[^\"']*[\"']\s*,")
        for root, _dirs, files in os.walk(self.repo_path):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                try:
                    with open(os.path.join(root, fn), errors="ignore") as fh:
                        content = fh.read()
                except OSError:
                    continue
                if pattern.search(content) or alt.search(content):
                    return True
        return False
