"""
Disagreement Engine
====================
Detects disagreement between agents so the Orchestrator can decide to
investigate further instead of naively averaging risk scores.

Disagreement is flagged when, for a comparable topic (same category or same
file/endpoint), agents' risk scores diverge beyond a threshold, or when their
qualitative severities are on opposite ends of the scale.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.evidence.store import Finding, Severity

SEVERITY_RANK = {
    Severity.INFO: 0, Severity.LOW: 1, Severity.MEDIUM: 2,
    Severity.HIGH: 3, Severity.CRITICAL: 4,
}

RISK_DISAGREEMENT_THRESHOLD = 0.35
SEVERITY_RANK_GAP_THRESHOLD = 2


@dataclass
class Disagreement:
    finding_a: str
    finding_b: str
    agent_a: str
    agent_b: str
    risk_a: float
    risk_b: float
    reason: str

    def to_dict(self):
        return self.__dict__.copy()


class DisagreementEngine:
    def detect(self, findings: list[Finding]) -> list[Disagreement]:
        disagreements = []
        # Compare pairs of findings that concern the same file (a good proxy
        # for "same part of the change") but come from different agents.
        for i, a in enumerate(findings):
            for b in findings[i + 1:]:
                if a.agent == b.agent:
                    continue
                # Only compare findings we can confirm concern the SAME file --
                # otherwise a Security finding about file X and a Performance
                # finding about unrelated file Y would be flagged as
                # "disagreement" when they simply concern different code.
                if not (a.file and b.file and a.file == b.file):
                    continue

                risk_gap = abs(a.risk - b.risk)
                sev_gap = abs(SEVERITY_RANK[a.severity] - SEVERITY_RANK[b.severity])

                if risk_gap >= RISK_DISAGREEMENT_THRESHOLD or sev_gap >= SEVERITY_RANK_GAP_THRESHOLD:
                    disagreements.append(Disagreement(
                        finding_a=a.finding_id, finding_b=b.finding_id,
                        agent_a=a.agent, agent_b=b.agent,
                        risk_a=a.risk, risk_b=b.risk,
                        reason=(
                            f"{a.agent} reports risk {a.risk:.2f} ({a.severity.value}) "
                            f"while {b.agent} reports risk {b.risk:.2f} ({b.severity.value}) "
                            f"for the same change area."
                        ),
                    ))
        return disagreements
