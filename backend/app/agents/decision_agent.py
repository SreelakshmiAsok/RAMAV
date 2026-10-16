"""
Decision Agent
==============
Converts (risk, confidence, disagreement state, evidence completeness) into
one of three explainable decisions: AUTO-APPROVE, AUTO-REJECT, or
HUMAN_REVIEW_REQUIRED.

IMPORTANT: this policy is entirely deterministic. An LLM is never allowed to
directly decide "approve this PR" -- it may only assist agents with
reasoning/explanation upstream. This keeps the final decision auditable and
is what we defend in the viva when asked "what happens if the model
hallucinates?": the hallucination can at worst produce a bad *finding*, which
still has to clear the deterministic decision policy and can be caught by
disagreement detection / low confidence -> HUMAN_REVIEW.

Thresholds are project policy parameters, not scientifically tuned:
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

THRESHOLDS = {
    "auto_approve_max_risk": 0.30,
    "auto_approve_min_confidence": 0.85,
    "auto_reject_min_risk": 0.75,
    "auto_reject_min_confidence": 0.80,
}


@dataclass
class Decision:
    outcome: str  # AUTO_APPROVE | AUTO_REJECT | HUMAN_REVIEW_REQUIRED
    risk: float
    confidence: float
    reasons: list[str] = field(default_factory=list)
    critical_override: bool = False
    disagreement_unresolved: bool = False

    def to_dict(self):
        return {
            "outcome": self.outcome,
            "risk": round(self.risk, 4),
            "confidence": round(self.confidence, 4),
            "reasons": self.reasons,
            "critical_override": self.critical_override,
            "disagreement_unresolved": self.disagreement_unresolved,
        }


class DecisionAgent:
    name = "decision_agent"

    def decide(
        self,
        *,
        risk: float,
        confidence: float,
        critical_override: bool,
        unresolved_disagreements: int,
        evidence_completeness: float,
        high_impact_change: bool = False,
    ) -> Decision:
        reasons: list[str] = []

        if critical_override:
            reasons.append("A critical finding overrides autonomous approval regardless of aggregate score.")
            return Decision(
                outcome="AUTO_REJECT", risk=risk, confidence=confidence,
                reasons=reasons, critical_override=True,
                disagreement_unresolved=unresolved_disagreements > 0,
            )

        if unresolved_disagreements > 0:
            reasons.append(
                f"Agents disagree on {unresolved_disagreements} finding(s) and available "
                f"evidence is insufficient to justify autonomous approval."
            )
            return Decision(
                outcome="HUMAN_REVIEW_REQUIRED", risk=risk, confidence=confidence,
                reasons=reasons, disagreement_unresolved=True,
            )

        if risk >= THRESHOLDS["auto_reject_min_risk"] and confidence >= THRESHOLDS["auto_reject_min_confidence"]:
            reasons.append(f"Overall risk {risk:.2f} exceeds the auto-reject threshold with high confidence.")
            return Decision(outcome="AUTO_REJECT", risk=risk, confidence=confidence, reasons=reasons)

        if (
            risk <= THRESHOLDS["auto_approve_max_risk"]
            and confidence >= THRESHOLDS["auto_approve_min_confidence"]
            and evidence_completeness >= 0.7
            and not high_impact_change
        ):
            reasons.append(f"Overall risk {risk:.2f} is low and confidence {confidence:.2f} is high with complete evidence.")
            return Decision(outcome="AUTO_APPROVE", risk=risk, confidence=confidence, reasons=reasons)

        if confidence < THRESHOLDS["auto_approve_min_confidence"]:
            reasons.append(f"Confidence {confidence:.2f} is below the autonomous-approval threshold.")
        if evidence_completeness < 0.7:
            reasons.append("Evidence completeness is insufficient for an autonomous decision.")
        if high_impact_change:
            reasons.append("This is a high-impact change; policy requires human sign-off.")
        if not reasons:
            reasons.append("Risk and confidence fall in the medium range that requires human judgement.")

        return Decision(outcome="HUMAN_REVIEW_REQUIRED", risk=risk, confidence=confidence, reasons=reasons)
