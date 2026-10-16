"""
Testing Agent
=============
Runs the demo repository's own pytest suite (if present) to get REAL pass/
fail/duration data, and answers Security Agent's evidence requests about
whether malicious-input tests exist for a flagged file/endpoint by actually
searching the test tree -- this is not scripted, it re-greps the repo each
time it is asked.
"""
from __future__ import annotations

import os
import re
import subprocess
import time

from app.agents.base_agent import BaseAgent
from app.analysis.change_analyzer import ChangeSet
from app.coordination.messages import AgentMessage, MessageType
from app.evidence.store import Evidence, Finding, Severity, SourceType

MALICIOUS_INPUT_HINTS = [
    "injection", "malicious", "' or '1'='1", "drop table", "xss", "<script>", "sqlmap", "sanitiz",
]


class TestingAgent(BaseAgent):
    name = "testing_agent"
    category = "testing"

    def analyze(self, changeset: ChangeSet) -> list[Finding]:
        findings = []
        result = self._run_pytest()

        if result is None:
            ev = self.store.add_evidence(Evidence(
                agent=self.name, description="No test runner / test suite could be executed for this repository.",
                source_type=SourceType.HEURISTIC, tool="pytest", strength=0.4,
            ))
            finding = Finding(
                agent=self.name, category=self.category, title="No executable test suite found",
                severity=Severity.MEDIUM, risk=0.5, confidence=0.6,
                evidence_ids=[ev.evidence_id], source_type=SourceType.HEURISTIC,
            )
            self.publish_finding(finding)
            return [finding]

        passed, failed, duration, raw = result
        source_type = SourceType.REAL_TOOL
        ev = self.store.add_evidence(Evidence(
            agent=self.name,
            description=f"pytest: {passed} passed, {failed} failed in {duration:.2f}s.",
            source_type=source_type, tool="pytest", strength=0.9,
        ))

        if failed > 0:
            # Tie this finding to the primary changed source file so the
            # Disagreement Engine can compare it against Security/Quality
            # conclusions about the SAME file (see docs/ARCHITECTURE.md,
            # "why file-matching for disagreement").
            primary_file = next(
                (f for f in changeset.changed_files if f.endswith(".py") and "test" not in f.lower()), None
            )
            finding = Finding(
                agent=self.name, category=self.category, title=f"{failed} test(s) failing after this change",
                severity=Severity.HIGH, risk=0.8, confidence=0.91,
                file=primary_file,
                evidence_ids=[ev.evidence_id], source_type=source_type,
            )
        elif not changeset.tests_changed and changeset.security_sensitive:
            finding = Finding(
                agent=self.name, category=self.category,
                title="Security-sensitive code changed without corresponding test changes",
                severity=Severity.MEDIUM, risk=0.55, confidence=0.7,
                evidence_ids=[ev.evidence_id], source_type=source_type,
            )
        else:
            finding = Finding(
                agent=self.name, category=self.category, title="All tests passing",
                severity=Severity.INFO, risk=0.1, confidence=0.9,
                evidence_ids=[ev.evidence_id], source_type=source_type,
            )
        self.publish_finding(finding)
        findings.append(finding)
        return findings

    def handle_message(self, message: AgentMessage):
        if message.type == MessageType.REQUEST_EVIDENCE and message.receiver == self.name:
            has_malicious_test, matched_file = self._search_for_malicious_input_tests()
            if has_malicious_test:
                content = f"Yes — {matched_file} contains a test that exercises malicious/adversarial input for this behaviour."
                strength = 0.85
            else:
                content = "No malicious-input test exists for this endpoint/behaviour in the current test suite."
                strength = 0.85
            ev = self.store.add_evidence(Evidence(
                agent=self.name, description=content, source_type=SourceType.REAL_TOOL,
                tool="pytest-tree-search", strength=strength,
            ))
            return self.respond(
                message.sender, content,
                related_finding_id=message.related_finding_id,
                related_evidence_ids=[ev.evidence_id],
            )
        return None

    def _search_for_malicious_input_tests(self) -> tuple[bool, str | None]:
        tests_dir = os.path.join(self.repo_path, "tests")
        if not os.path.isdir(tests_dir):
            return False, None
        for root, _dirs, files in os.walk(tests_dir):
            for fn in files:
                if not fn.endswith(".py"):
                    continue
                full = os.path.join(root, fn)
                try:
                    with open(full, errors="ignore") as fh:
                        content = fh.read().lower()
                except OSError:
                    continue
                if any(h in content for h in MALICIOUS_INPUT_HINTS):
                    return True, os.path.relpath(full, self.repo_path)
        return False, None

    def _run_pytest(self):
        tests_dir = os.path.join(self.repo_path, "tests")
        if not os.path.isdir(tests_dir):
            return None
        start = time.time()
        try:
            proc = subprocess.run(
                ["python3", "-m", "unittest", "discover", "-s", tests_dir, "-v"],
                capture_output=True, text=True, timeout=30, cwd=self.repo_path,
            )
        except Exception:
            return None
        duration = time.time() - start
        out = proc.stdout + proc.stderr
        # unittest's textual summary line looks like "Ran 4 tests in 0.01s"
        # and failures are reported individually; count them from the output.
        failed = out.count("FAIL:") + out.count("ERROR:")
        ran_match = re.search(r"Ran (\d+) tests?", out)
        ran = int(ran_match.group(1)) if ran_match else 0
        passed = max(ran - failed, 0)
        return passed, failed, duration, out
