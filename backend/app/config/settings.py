"""
Central, documented configuration. These are project POLICY parameters, not
scientifically-tuned constants -- see docs/ARCHITECTURE.md and
docs/VIVA_PREPARATION.md ("are these thresholds scientifically optimal?").
Exposed via GET /api/system/config so the dashboard can display exactly
what policy produced a given decision.
"""
from app.confidence.engine import WEIGHTS as CONFIDENCE_WEIGHTS
from app.agents.decision_agent import THRESHOLDS as DECISION_THRESHOLDS
from app.risk.engine import DEFAULT_WEIGHTS as RISK_WEIGHTS


def full_config() -> dict:
    return {
        "risk_weights": RISK_WEIGHTS,
        "confidence_weights": CONFIDENCE_WEIGHTS,
        "decision_thresholds": DECISION_THRESHOLDS,
        "investigation": {
            "max_actions_per_run": 12,
            "priority_formula": "severity * uncertainty * impact / estimated_cost",
        },
        "disagreement": {
            "risk_gap_threshold": 0.35,
            "severity_rank_gap_threshold": 2,
        },
    }
