"""
Confidence Engine
=================
Deliberately NOT "ask the LLM how confident it is". Confidence is computed
from explicit, inspectable factors so the dashboard can show a breakdown like:

    Confidence = 0.91
      agent_confidence      0.90
      evidence_strength      0.95
      tool_reliability       0.95
      agreement_factor       0.90
      evidence_completeness  0.85
      uncertainty_penalty   -0.04

Formula (documented, not "scientifically optimal" -- a project policy):

    raw = ( w1*agent_confidence + w2*evidence_strength + w3*tool_reliability
            + w4*agreement_factor + w5*evidence_completeness )
    confidence = clamp(raw - uncertainty_penalty, 0, 1)

Weights sum to 1 across the five positive factors.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.evidence.store import Finding, Evidence, SourceType

WEIGHTS = {
    "agent_confidence": 0.30,
    "evidence_strength": 0.25,
    "tool_reliability": 0.20,
    "agreement_factor": 0.15,
    "evidence_completeness": 0.10,
}

TOOL_RELIABILITY = {
    SourceType.REAL_TOOL: 0.95,
    SourceType.HEURISTIC: 0.70,
    SourceType.LLM_ANALYSIS: 0.60,
    SourceType.MOCK_DEMO: 0.50,
}


@dataclass
class ConfidenceBreakdown:
    confidence: float
    agent_confidence: float
    evidence_strength: float
    tool_reliability: float
    agreement_factor: float
    evidence_completeness: float
    uncertainty_penalty: float

    def to_dict(self):
        return {
            "confidence": round(self.confidence, 4),
            "components": {
                "agent_confidence": round(self.agent_confidence, 4),
                "evidence_strength": round(self.evidence_strength, 4),
                "tool_reliability": round(self.tool_reliability, 4),
                "agreement_factor": round(self.agreement_factor, 4),
                "evidence_completeness": round(self.evidence_completeness, 4),
                "uncertainty_penalty": round(-self.uncertainty_penalty, 4),
            },
        }


class ConfidenceEngine:
    def compute_for_finding(
        self,
        finding: Finding,
        evidence_items: list[Evidence],
        *,
        agreement_factor: float,
        open_questions_for_finding: int,
    ) -> ConfidenceBreakdown:
        agent_confidence = finding.confidence

        evidence_strength = (
            sum(e.strength for e in evidence_items) / len(evidence_items)
            if evidence_items else 0.3
        )

        if evidence_items:
            tool_reliability = sum(
                TOOL_RELIABILITY.get(SourceType(e.source_type) if not isinstance(e.source_type, SourceType) else e.source_type, 0.6)
                for e in evidence_items
            ) / len(evidence_items)
        else:
            tool_reliability = TOOL_RELIABILITY.get(finding.source_type, 0.6)

        # completeness: even a single direct piece of evidence already
        # covers the basic case; each additional independent item adds
        # further completeness, saturating at 1.0.
        evidence_completeness = min(1.0, 0.50 + 0.20 * len(evidence_items)) if evidence_items else 0.35

        uncertainty_penalty = 0.05 * open_questions_for_finding

        raw = (
            WEIGHTS["agent_confidence"] * agent_confidence
            + WEIGHTS["evidence_strength"] * evidence_strength
            + WEIGHTS["tool_reliability"] * tool_reliability
            + WEIGHTS["agreement_factor"] * agreement_factor
            + WEIGHTS["evidence_completeness"] * evidence_completeness
        )
        confidence = max(0.0, min(1.0, raw - uncertainty_penalty))

        return ConfidenceBreakdown(
            confidence=confidence,
            agent_confidence=agent_confidence,
            evidence_strength=evidence_strength,
            tool_reliability=tool_reliability,
            agreement_factor=agreement_factor,
            evidence_completeness=evidence_completeness,
            uncertainty_penalty=uncertainty_penalty,
        )

    def overall(self, breakdowns: list[ConfidenceBreakdown], mode: str = "min") -> float:
        if not breakdowns:
            return 0.5
        if mode == "min":
            # weakest link: a single poorly-evidenced, high-severity finding
            # cannot be hidden by many well-evidenced low-risk ones.
            return min(b.confidence for b in breakdowns)
        # mode == "mean": used when there is no medium+ severity finding at
        # all (e.g. a genuinely safe change) -- there is no single risky
        # claim whose weakest link should dominate the score.
        return sum(b.confidence for b in breakdowns) / len(breakdowns)
