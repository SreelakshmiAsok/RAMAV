"""
Risk Engine
===========
Aggregates per-category risk (security/testing/dependency/performance/quality)
into a single overall risk score using configurable weights, plus explicit
"critical finding override" rules so that a single critical security issue
can never be averaged away into an AUTO-APPROVE.

overall_risk = sum(category_risk * category_weight)   [renormalised over
categories that actually produced a finding]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.evidence.store import Finding, Severity

DEFAULT_WEIGHTS = {
    "security": 0.35,
    "testing": 0.25,
    "dependency": 0.15,
    "performance": 0.15,
    "quality": 0.10,
}


@dataclass
class RiskBreakdown:
    overall_risk: float
    category_scores: dict  # category -> risk in [0,1]
    weights_used: dict
    critical_override: bool
    critical_reason: Optional[str] = None

    def to_dict(self):
        return {
            "overall_risk": round(self.overall_risk, 4),
            "category_scores": {k: round(v, 4) for k, v in self.category_scores.items()},
            "weights_used": self.weights_used,
            "critical_override": self.critical_override,
            "critical_reason": self.critical_reason,
        }


class RiskEngine:
    def __init__(self, weights: dict = None):
        self.weights = dict(weights or DEFAULT_WEIGHTS)

    def _category_risk(self, findings: list[Finding]) -> float:
        if not findings:
            return 0.0
        # a category's risk is the max risk among its open findings, not the
        # average -- one severe finding should not be diluted by several
        # minor ones from the same agent.
        return max(f.risk for f in findings)

    def compute(self, findings: list[Finding]) -> RiskBreakdown:
        by_category: dict[str, list[Finding]] = {}
        for f in findings:
            by_category.setdefault(f.category, []).append(f)

        category_scores = {cat: self._category_risk(fs) for cat, fs in by_category.items()}

        active_weights = {c: w for c, w in self.weights.items() if c in category_scores}
        total_w = sum(active_weights.values()) or 1.0
        normalised = {c: w / total_w for c, w in active_weights.items()}

        overall = sum(category_scores[c] * normalised[c] for c in category_scores) if category_scores else 0.0

        critical_override = False
        critical_reason = None
        for f in findings:
            if f.severity == Severity.CRITICAL or (f.category == "security" and f.risk >= 0.85):
                critical_override = True
                critical_reason = f"Critical finding {f.finding_id} ({f.title}) blocks autonomous approval regardless of overall score."
                overall = max(overall, 0.80)
                break

        return RiskBreakdown(
            overall_risk=min(overall, 1.0),
            category_scores=category_scores,
            weights_used=normalised,
            critical_override=critical_override,
            critical_reason=critical_reason,
        )
