"""
Evidence Store
==============
Holds every Finding and its supporting Evidence for one analysis run.

Every finding is required to declare a `source_type` so the dashboard can
show the user exactly where a number came from. This directly implements the
"NO FABRICATION RULE": nothing is allowed to silently claim to be a real tool
result when it is a heuristic or a demo fixture.
"""
from __future__ import annotations

import itertools
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class SourceType(str, Enum):
    REAL_TOOL = "REAL_TOOL"          # e.g. actual Semgrep / pytest / git output
    LLM_ANALYSIS = "LLM_ANALYSIS"    # actual local LLM call (Ollama)
    HEURISTIC = "HEURISTIC"          # deterministic rule-based fallback logic
    MOCK_DEMO = "MOCK_DEMO"          # scripted fixture data for a demo scenario


class Severity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


_counter = itertools.count(1)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{next(_counter):05d}-{uuid.uuid4().hex[:6]}"


@dataclass
class Evidence:
    agent: str
    description: str
    source_type: SourceType
    tool: Optional[str] = None
    file: Optional[str] = None
    line: Optional[int] = None
    strength: float = 0.5  # 0..1, how strong/direct this piece of evidence is
    evidence_id: str = field(default_factory=lambda: _new_id("EVID"))
    created_at: float = field(default_factory=time.time)

    def to_dict(self):
        d = asdict(self)
        d["source_type"] = self.source_type.value
        return d


@dataclass
class Finding:
    agent: str
    category: str  # security | testing | quality | dependency | performance
    title: str
    severity: Severity
    risk: float          # 0..1
    confidence: float    # 0..1
    file: Optional[str] = None
    line: Optional[int] = None
    evidence_ids: list[str] = field(default_factory=list)
    source_type: SourceType = SourceType.HEURISTIC
    status: str = "OPEN"  # OPEN | REASSESSED | RESOLVED | REJECTED
    finding_id: str = field(default_factory=lambda: _new_id("FIND"))
    history: list[dict] = field(default_factory=list)  # audit trail of reassessments
    created_at: float = field(default_factory=time.time)

    def reassess(self, *, risk: float = None, confidence: float = None, reason: str = ""):
        self.history.append({
            "risk_before": self.risk, "confidence_before": self.confidence,
            "risk_after": risk if risk is not None else self.risk,
            "confidence_after": confidence if confidence is not None else self.confidence,
            "reason": reason, "timestamp": time.time(),
        })
        if risk is not None:
            self.risk = risk
        if confidence is not None:
            self.confidence = confidence
        self.status = "REASSESSED"

    def to_dict(self):
        d = asdict(self)
        d["severity"] = self.severity.value
        d["source_type"] = self.source_type.value
        return d


class EvidenceStore:
    def __init__(self):
        self.findings: dict[str, Finding] = {}
        self.evidence: dict[str, Evidence] = {}

    def add_evidence(self, ev: Evidence) -> Evidence:
        self.evidence[ev.evidence_id] = ev
        return ev

    def add_finding(self, finding: Finding) -> Finding:
        self.findings[finding.finding_id] = finding
        return finding

    def get(self, finding_id: str) -> Optional[Finding]:
        return self.findings.get(finding_id)

    def by_category(self, category: str) -> list[Finding]:
        return [f for f in self.findings.values() if f.category == category]

    def by_agent(self, agent: str) -> list[Finding]:
        return [f for f in self.findings.values() if f.agent == agent]

    def all_findings(self) -> list[Finding]:
        return list(self.findings.values())

    def evidence_for(self, finding: Finding) -> list[Evidence]:
        return [self.evidence[eid] for eid in finding.evidence_ids if eid in self.evidence]

    def to_dict(self) -> dict:
        return {
            "findings": [f.to_dict() for f in self.findings.values()],
            "evidence": [e.to_dict() for e in self.evidence.values()],
        }
