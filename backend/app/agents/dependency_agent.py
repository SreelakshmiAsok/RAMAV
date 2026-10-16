"""
Dependency Agent
================
Inspects requirements.txt / package.json for the changeset and flags newly
added or unpinned dependencies. Deliberately simple: this is a real,
inspectable heuristic rather than a full CVE-database lookup (which would
need network access we can't rely on for the classroom demo).
"""
from __future__ import annotations

import json
import os
import re

from app.agents.base_agent import BaseAgent
from app.analysis.change_analyzer import ChangeSet
from app.evidence.store import Evidence, Finding, Severity, SourceType


class DependencyAgent(BaseAgent):
    name = "dependency_agent"
    category = "dependency"

    def analyze(self, changeset: ChangeSet) -> list[Finding]:
        findings = []
        unpinned = []
        added = []

        for rel in changeset.dependency_files_changed:
            full = os.path.join(self.repo_path, rel)
            if not os.path.isfile(full):
                continue
            if rel.endswith("requirements.txt"):
                with open(full, errors="ignore") as fh:
                    for line in fh:
                        line = line.strip()
                        if not line or line.startswith("#"):
                            continue
                        added.append(line)
                        if "==" not in line and ">=" not in line:
                            unpinned.append(line)
            elif rel.endswith("package.json"):
                try:
                    data = json.loads(open(full).read())
                    for name, ver in {**data.get("dependencies", {}), **data.get("devDependencies", {})}.items():
                        added.append(f"{name}@{ver}")
                        if ver.strip().startswith("*") or ver.strip() == "latest":
                            unpinned.append(f"{name}@{ver}")
                except (OSError, json.JSONDecodeError):
                    pass

        source_type = SourceType.HEURISTIC
        if not changeset.dependency_files_changed:
            ev = self.store.add_evidence(Evidence(
                agent=self.name, description="No dependency manifest changes detected.",
                source_type=source_type, tool="manifest-diff", strength=0.8,
            ))
            finding = Finding(
                agent=self.name, category=self.category, title="No dependency changes",
                severity=Severity.INFO, risk=0.05, confidence=0.9,
                evidence_ids=[ev.evidence_id], source_type=source_type,
            )
        elif unpinned:
            ev = self.store.add_evidence(Evidence(
                agent=self.name,
                description=f"Unpinned/loose dependency versions detected: {', '.join(unpinned)}",
                source_type=source_type, tool="manifest-diff", strength=0.7,
            ))
            finding = Finding(
                agent=self.name, category=self.category, title="Unpinned dependency versions",
                severity=Severity.MEDIUM, risk=0.4, confidence=0.75,
                evidence_ids=[ev.evidence_id], source_type=source_type,
            )
        else:
            ev = self.store.add_evidence(Evidence(
                agent=self.name, description=f"Dependencies changed but all versions are pinned: {', '.join(added)}",
                source_type=source_type, tool="manifest-diff", strength=0.7,
            ))
            finding = Finding(
                agent=self.name, category=self.category, title="Dependency changes look safe",
                severity=Severity.LOW, risk=0.2, confidence=0.75,
                evidence_ids=[ev.evidence_id], source_type=source_type,
            )
        self.publish_finding(finding)
        findings.append(finding)
        return findings
