import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agents.decision_agent import DecisionAgent
from app.confidence.engine import ConfidenceEngine
from app.coordination.disagreement import DisagreementEngine
from app.evidence.store import Evidence, Finding, Severity, SourceType
from app.risk.engine import RiskEngine
from app.search.investigation import ActionType, InvestigationAction, InvestigationPlanner


class TestRiskEngine(unittest.TestCase):
    def test_empty_findings_gives_zero_risk(self):
        rb = RiskEngine().compute([])
        self.assertEqual(rb.overall_risk, 0.0)
        self.assertFalse(rb.critical_override)

    def test_weighted_aggregation(self):
        findings = [
            Finding(agent="security_agent", category="security", title="x", severity=Severity.MEDIUM, risk=0.4, confidence=0.8),
            Finding(agent="testing_agent", category="testing", title="y", severity=Severity.LOW, risk=0.2, confidence=0.8),
        ]
        rb = RiskEngine().compute(findings)
        # only security + testing weights active, renormalised to sum 1
        expected = 0.4 * (0.35 / 0.60) + 0.2 * (0.25 / 0.60)
        self.assertAlmostEqual(rb.overall_risk, expected, places=4)

    def test_critical_finding_forces_override(self):
        findings = [
            Finding(agent="security_agent", category="security", title="critical bug",
                    severity=Severity.CRITICAL, risk=0.5, confidence=0.9),
        ]
        rb = RiskEngine().compute(findings)
        self.assertTrue(rb.critical_override)
        self.assertGreaterEqual(rb.overall_risk, 0.80)

    def test_category_risk_uses_max_not_average(self):
        findings = [
            Finding(agent="security_agent", category="security", title="a", severity=Severity.LOW, risk=0.1, confidence=0.8),
            Finding(agent="security_agent", category="security", title="b", severity=Severity.HIGH, risk=0.9, confidence=0.8),
        ]
        rb = RiskEngine().compute(findings)
        self.assertEqual(rb.category_scores["security"], 0.9)


class TestConfidenceEngine(unittest.TestCase):
    def test_more_evidence_increases_completeness(self):
        engine = ConfidenceEngine()
        finding = Finding(agent="security_agent", category="security", title="x",
                           severity=Severity.HIGH, risk=0.8, confidence=0.8)
        ev1 = [Evidence(agent="security_agent", description="one", source_type=SourceType.REAL_TOOL, strength=0.8)]
        ev3 = ev1 * 3
        bd1 = engine.compute_for_finding(finding, ev1, agreement_factor=0.9, open_questions_for_finding=0)
        bd3 = engine.compute_for_finding(finding, ev3, agreement_factor=0.9, open_questions_for_finding=0)
        self.assertGreaterEqual(bd3.confidence, bd1.confidence)

    def test_open_questions_reduce_confidence(self):
        engine = ConfidenceEngine()
        finding = Finding(agent="security_agent", category="security", title="x",
                           severity=Severity.HIGH, risk=0.8, confidence=0.8)
        ev = [Evidence(agent="security_agent", description="one", source_type=SourceType.REAL_TOOL, strength=0.8)]
        bd_no_q = engine.compute_for_finding(finding, ev, agreement_factor=0.9, open_questions_for_finding=0)
        bd_with_q = engine.compute_for_finding(finding, ev, agreement_factor=0.9, open_questions_for_finding=2)
        self.assertLess(bd_with_q.confidence, bd_no_q.confidence)

    def test_real_tool_more_reliable_than_mock(self):
        engine = ConfidenceEngine()
        finding = Finding(agent="security_agent", category="security", title="x",
                           severity=Severity.HIGH, risk=0.8, confidence=0.8)
        ev_real = [Evidence(agent="security_agent", description="x", source_type=SourceType.REAL_TOOL, strength=0.8)]
        ev_mock = [Evidence(agent="security_agent", description="x", source_type=SourceType.MOCK_DEMO, strength=0.8)]
        bd_real = engine.compute_for_finding(finding, ev_real, agreement_factor=0.9, open_questions_for_finding=0)
        bd_mock = engine.compute_for_finding(finding, ev_mock, agreement_factor=0.9, open_questions_for_finding=0)
        self.assertGreater(bd_real.tool_reliability, bd_mock.tool_reliability)

    def test_overall_min_mode_is_weakest_link(self):
        engine = ConfidenceEngine()
        f1 = Finding(agent="a", category="security", title="x", severity=Severity.HIGH, risk=0.8, confidence=0.95)
        f2 = Finding(agent="b", category="testing", title="y", severity=Severity.HIGH, risk=0.8, confidence=0.3)
        ev = [Evidence(agent="a", description="x", source_type=SourceType.REAL_TOOL, strength=0.9)]
        bd1 = engine.compute_for_finding(f1, ev, agreement_factor=0.9, open_questions_for_finding=0)
        bd2 = engine.compute_for_finding(f2, ev, agreement_factor=0.9, open_questions_for_finding=0)
        overall = engine.overall([bd1, bd2], mode="min")
        self.assertEqual(overall, min(bd1.confidence, bd2.confidence))


class TestDisagreementEngine(unittest.TestCase):
    def test_same_file_large_risk_gap_is_disagreement(self):
        f1 = Finding(agent="security_agent", category="security", title="x", severity=Severity.LOW,
                     risk=0.15, confidence=0.8, file="app/x.py")
        f2 = Finding(agent="testing_agent", category="testing", title="y", severity=Severity.HIGH,
                     risk=0.8, confidence=0.9, file="app/x.py")
        disagreements = DisagreementEngine().detect([f1, f2])
        self.assertEqual(len(disagreements), 1)

    def test_different_files_not_compared(self):
        f1 = Finding(agent="security_agent", category="security", title="x", severity=Severity.LOW,
                     risk=0.1, confidence=0.8, file="app/x.py")
        f2 = Finding(agent="performance_agent", category="performance", title="y", severity=Severity.HIGH,
                     risk=0.9, confidence=0.9, file="app/y.py")
        disagreements = DisagreementEngine().detect([f1, f2])
        self.assertEqual(len(disagreements), 0)

    def test_same_agent_never_disagrees_with_itself(self):
        f1 = Finding(agent="security_agent", category="security", title="x", severity=Severity.LOW,
                     risk=0.1, confidence=0.8, file="app/x.py")
        f2 = Finding(agent="security_agent", category="security", title="y", severity=Severity.HIGH,
                     risk=0.9, confidence=0.9, file="app/x.py")
        disagreements = DisagreementEngine().detect([f1, f2])
        self.assertEqual(len(disagreements), 0)


class TestDecisionAgent(unittest.TestCase):
    def setUp(self):
        self.agent = DecisionAgent()

    def test_low_risk_high_confidence_auto_approves(self):
        d = self.agent.decide(risk=0.1, confidence=0.9, critical_override=False,
                               unresolved_disagreements=0, evidence_completeness=0.9)
        self.assertEqual(d.outcome, "AUTO_APPROVE")

    def test_critical_override_forces_reject_even_with_low_aggregate_risk(self):
        d = self.agent.decide(risk=0.2, confidence=0.9, critical_override=True,
                               unresolved_disagreements=0, evidence_completeness=0.9)
        self.assertEqual(d.outcome, "AUTO_REJECT")

    def test_unresolved_disagreement_forces_human_review(self):
        d = self.agent.decide(risk=0.1, confidence=0.95, critical_override=False,
                               unresolved_disagreements=1, evidence_completeness=0.95)
        self.assertEqual(d.outcome, "HUMAN_REVIEW_REQUIRED")

    def test_disagreement_is_not_simply_averaged_away(self):
        # Even though risk/confidence individually look "approvable", a
        # single unresolved disagreement must NOT be averaged into approval.
        d = self.agent.decide(risk=0.05, confidence=0.99, critical_override=False,
                               unresolved_disagreements=1, evidence_completeness=1.0)
        self.assertNotEqual(d.outcome, "AUTO_APPROVE")

    def test_medium_risk_requires_human_review(self):
        d = self.agent.decide(risk=0.5, confidence=0.6, critical_override=False,
                               unresolved_disagreements=0, evidence_completeness=0.6)
        self.assertEqual(d.outcome, "HUMAN_REVIEW_REQUIRED")


class TestInvestigationPlanner(unittest.TestCase):
    def test_higher_priority_action_popped_first(self):
        planner = InvestigationPlanner()
        low = InvestigationAction(type=ActionType.ASK_QUESTION, target_agent="quality_agent",
                                   description="low", severity="LOW", uncertainty=0.2, impact=0.2)
        high = InvestigationAction(type=ActionType.REQUEST_EVIDENCE, target_agent="testing_agent",
                                    description="high", severity="HIGH", uncertainty=0.9, impact=0.9)
        planner.push(low)
        planner.push(high)
        first = planner.pop_best()
        self.assertIs(first, high)

    def test_budget_is_respected(self):
        planner = InvestigationPlanner(max_actions=2)
        for i in range(5):
            planner.push(InvestigationAction(type=ActionType.ASK_QUESTION, target_agent="x",
                                              description=str(i), severity="LOW", uncertainty=0.5, impact=0.5))
        popped = 0
        while planner.has_next():
            planner.pop_best()
            popped += 1
        self.assertEqual(popped, 2)


if __name__ == "__main__":
    unittest.main()
