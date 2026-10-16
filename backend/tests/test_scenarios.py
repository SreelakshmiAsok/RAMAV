import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.agents.orchestrator import Orchestrator
from app.services.repair_service import run_repair_and_revalidate

SCENARIOS_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "demo-repository", "scenarios")


def _run(scenario_name):
    path = os.path.join(SCENARIOS_DIR, scenario_name)
    orch = Orchestrator(path, f"PR-{scenario_name}")
    return orch, orch.run()


class TestSafeScenario(unittest.TestCase):
    def test_safe_pr_is_auto_approved(self):
        _, result = _run("safe")
        self.assertEqual(result["decision"]["outcome"], "AUTO_APPROVE")
        self.assertLess(result["decision"]["risk"], 0.30)
        self.assertGreaterEqual(result["decision"]["confidence"], 0.85)


class TestSqlInjectionScenario(unittest.TestCase):
    def test_sql_injection_is_auto_rejected(self):
        orch, result = _run("sql_injection")
        self.assertEqual(result["decision"]["outcome"], "AUTO_REJECT")
        self.assertTrue(result["decision"]["critical_override"])

    def test_security_agent_actually_asked_testing_agent(self):
        _, result = _run("sql_injection")
        types = [m["type"] for m in result["messages"]]
        self.assertIn("REQUEST_EVIDENCE", types)
        self.assertIn("RESPONSE", types)
        self.assertIn("REASSESS", types)

    def test_security_finding_reassessed_upward(self):
        orch, result = _run("sql_injection")
        sec_findings = [f for f in result["findings"] if f["agent"] == "security_agent" and f["severity"] == "HIGH"]
        self.assertEqual(len(sec_findings), 1)
        self.assertGreater(len(sec_findings[0]["history"]), 0, "Security finding should show a reassessment audit trail")

    def test_quality_challenged_security_about_conventions(self):
        _, result = _run("sql_injection")
        challenges = [m for m in result["messages"] if m["type"] == "CHALLENGE"]
        self.assertTrue(any(c["sender"] == "quality_agent" for c in challenges))


class TestDisagreementScenario(unittest.TestCase):
    def test_disagreement_triggers_human_review(self):
        _, result = _run("disagreement")
        self.assertEqual(result["decision"]["outcome"], "HUMAN_REVIEW_REQUIRED")
        self.assertTrue(result["decision"]["disagreement_unresolved"])

    def test_disagreement_message_was_published(self):
        _, result = _run("disagreement")
        types = [m["type"] for m in result["messages"]]
        self.assertIn("DISAGREEMENT", types)
        self.assertIn("ESCALATE", types)

    def test_testing_finding_is_based_on_real_failing_test(self):
        _, result = _run("disagreement")
        testing_findings = [f for f in result["findings"] if f["agent"] == "testing_agent"]
        self.assertTrue(any("failing" in f["title"].lower() for f in testing_findings))
        self.assertTrue(any(f["source_type"] == "REAL_TOOL" for f in testing_findings))


class TestLowEvidenceScenario(unittest.TestCase):
    def test_low_evidence_escalates_to_human_review(self):
        _, result = _run("low_evidence")
        self.assertEqual(result["decision"]["outcome"], "HUMAN_REVIEW_REQUIRED")


class TestRepairScenario(unittest.TestCase):
    def test_repair_is_verified_and_original_pr_was_rejected(self):
        result = run_repair_and_revalidate(os.path.join(SCENARIOS_DIR, "repair"), "PR-repair")
        self.assertEqual(result["pre_repair"]["decision"]["outcome"], "AUTO_REJECT")
        self.assertTrue(result["repair_attempted"])
        self.assertTrue(result["repair_verified"])

    def test_repair_never_trusted_without_revalidation(self):
        # The service must always re-run the FULL pipeline post-patch,
        # never just check "did the patcher say it succeeded".
        result = run_repair_and_revalidate(os.path.join(SCENARIOS_DIR, "repair"), "PR-repair")
        self.assertIsNotNone(result["post_repair"])
        self.assertIn("decision", result["post_repair"])


class TestNoFabrication(unittest.TestCase):
    def test_every_finding_declares_a_source_type(self):
        for scenario in ["safe", "sql_injection", "disagreement", "low_evidence"]:
            _, result = _run(scenario)
            for f in result["findings"]:
                self.assertIn(f["source_type"], ("REAL_TOOL", "LLM_ANALYSIS", "HEURISTIC", "MOCK_DEMO"))

    def test_every_evidence_item_declares_a_source_type(self):
        for scenario in ["safe", "sql_injection"]:
            _, result = _run(scenario)
            for e in result["evidence"]:
                self.assertIn(e["source_type"], ("REAL_TOOL", "LLM_ANALYSIS", "HEURISTIC", "MOCK_DEMO"))


if __name__ == "__main__":
    unittest.main()
