#!/usr/bin/env python3
"""Runs three methods against evaluation/dataset.json and reports what
actually happened. Nothing here is hand-edited or fabricated."""
import json, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "backend"))

from app.agents.orchestrator import Orchestrator
from app.agents.security_agent import SecurityAgent
from app.analysis.change_analyzer import ChangeAnalyzer
from app.coordination.messages import MessageBus
from app.evidence.store import EvidenceStore, Severity
from app.risk.engine import DEFAULT_WEIGHTS


def baseline_a(path):
    cs = ChangeAnalyzer().analyze_directory(path, "eval")
    store = EvidenceStore()
    SecurityAgent(MessageBus(), store, path).analyze(cs)
    bad = any(f.severity in (Severity.HIGH, Severity.CRITICAL) for f in store.all_findings())
    return "AUTO_REJECT" if bad else "AUTO_APPROVE"


def baseline_b(path):
    orch = Orchestrator(path, "eval")
    cs = ChangeAnalyzer().analyze_directory(path, "eval")
    for agent in orch.agents.values():  # independent, no messaging/investigation
        agent.analyze(cs)
    findings = orch.store.all_findings()
    cat = {}
    for f in findings:
        cat[f.category] = max(cat.get(f.category, 0), f.risk)
    avg = sum(cat.values()) / len(cat) if cat else 0
    return "AUTO_REJECT" if avg >= 0.6 else "AUTO_APPROVE" if avg < 0.3 else "AUTO_APPROVE_MEDIUM"


def proposed(path):
    return Orchestrator(path, "eval").run()["decision"]["outcome"]


def main():
    data = json.load(open(os.path.join(ROOT, "evaluation", "dataset.json")))
    rows = []
    for item in data:
        path = os.path.join(ROOT, item["path"])
        row = {"scenario": item["scenario"], "expected": item["expected_outcome"],
               "baseline_a_static_only": baseline_a(path),
               "baseline_b_naive_average": baseline_b(path),
               "proposed_ramav": proposed(path)}
        rows.append(row)
    summary = {}
    for m in ("baseline_a_static_only", "baseline_b_naive_average", "proposed_ramav"):
        summary[m] = {
            "exact_match": sum(r[m] == r["expected"] for r in rows),
            "total": len(rows),
            "unsafe_auto_approvals": sum(
                r[m].startswith("AUTO_APPROVE") and r["expected"] != "AUTO_APPROVE" for r in rows),
        }
    out = {"note": "Only 5 illustrative scenarios; not statistically meaningful.",
           "rows": rows, "summary": summary}
    json.dump(out, open(os.path.join(ROOT, "evaluation", "results.json"), "w"), indent=2)
    print(f"{'scenario':<15}{'expected':<24}{'A static':<24}{'B avg':<24}{'RAMAV':<24}")
    for r in rows:
        print(f"{r['scenario']:<15}{r['expected']:<24}{r['baseline_a_static_only']:<24}"
              f"{r['baseline_b_naive_average']:<24}{r['proposed_ramav']:<24}")
    print(json.dumps(summary, indent=2))
    print(out["note"])


if __name__ == "__main__":
    main()
