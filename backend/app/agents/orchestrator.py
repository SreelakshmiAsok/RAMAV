"""
Orchestrator
============
The central coordination component. This is NOT "call every agent once and
average the results" -- it holds state (OrchestratorState), runs a
best-first investigation search (app.search.investigation) to decide what to
do next, drives real agent-to-agent messages (REQUEST_EVIDENCE, CHALLENGE,
QUESTION, REASSESS), detects disagreement, and only then hands off to the
Risk / Confidence / Decision engines.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from app.agents.decision_agent import DecisionAgent
from app.agents.dependency_agent import DependencyAgent
from app.agents.performance_agent import PerformanceAgent
from app.agents.quality_agent import QualityAgent
from app.agents.security_agent import SecurityAgent
from app.agents.testing_agent import TestingAgent
from app.analysis.change_analyzer import ChangeAnalyzer, ChangeSet
from app.confidence.engine import ConfidenceEngine
from app.coordination.disagreement import Disagreement, DisagreementEngine
from app.coordination.messages import AgentMessage, MessageBus, MessageType, Priority
from app.evidence.store import EvidenceStore, Finding, Severity, SourceType
from app.risk.engine import RiskEngine
from app.search.investigation import ActionType, InvestigationAction, InvestigationPlanner

SEVERITY_TO_STR = {s: s.value for s in Severity}


@dataclass
class OrchestratorState:
    findings: list = field(default_factory=list)
    messages: list = field(default_factory=list)
    open_questions: list = field(default_factory=list)
    disagreements: list = field(default_factory=list)
    unresolved_disagreements: int = 0
    confidence: dict = field(default_factory=dict)
    risk: dict = field(default_factory=dict)
    next_actions: list = field(default_factory=list)
    completed_actions: list = field(default_factory=list)

    def to_dict(self):
        return {
            "open_questions": self.open_questions,
            "disagreements": [d.to_dict() if isinstance(d, Disagreement) else d for d in self.disagreements],
            "unresolved_disagreements": self.unresolved_disagreements,
            "confidence": self.confidence,
            "risk": self.risk,
            "next_actions": [a.to_dict() if hasattr(a, "to_dict") else a for a in self.next_actions],
            "completed_actions": [a.to_dict() if hasattr(a, "to_dict") else a for a in self.completed_actions],
        }


class Orchestrator:
    def __init__(self, repo_path: str, pr_id: str):
        self.repo_path = repo_path
        self.pr_id = pr_id
        self.bus = MessageBus()
        self.store = EvidenceStore()
        self.state = OrchestratorState()

        self.agents = {
            "security_agent": SecurityAgent(self.bus, self.store, repo_path),
            "testing_agent": TestingAgent(self.bus, self.store, repo_path),
            "quality_agent": QualityAgent(self.bus, self.store, repo_path),
            "dependency_agent": DependencyAgent(self.bus, self.store, repo_path),
            "performance_agent": PerformanceAgent(self.bus, self.store, repo_path),
        }
        self.risk_engine = RiskEngine()
        self.confidence_engine = ConfidenceEngine()
        self.disagreement_engine = DisagreementEngine()
        self.decision_agent = DecisionAgent()
        self.planner = InvestigationPlanner(max_actions=12)

        self.changeset: ChangeSet | None = None
        self.decision = None

    # ------------------------------------------------------------------
    def run(self) -> dict:
        t0 = time.time()
        self.changeset = ChangeAnalyzer().analyze_directory(self.repo_path, self.pr_id)
        self.bus.publish(AgentMessage(
            sender="orchestrator", type=MessageType.TASK,
            content=f"Change analyzed: {self.changeset.files_changed} file(s), "
                    f"security_sensitive={self.changeset.security_sensitive}, "
                    f"database_access={self.changeset.database_access}, "
                    f"tests_changed={self.changeset.tests_changed}.",
        ))

        # 1. Dispatch every specialized agent once -- this alone would be
        #    "independent agents", which the spec explicitly says is
        #    insufficient. The coordination happens in step 2 onward.
        for agent_name, agent in self.agents.items():
            self.bus.publish(AgentMessage(sender="orchestrator", receiver=agent_name, type=MessageType.TASK,
                                           content=f"Analyze changeset for PR {self.pr_id}."))
            agent.analyze(self.changeset)

        # 2. Look at the initial findings and enqueue candidate investigation
        #    actions with real priority scores (severity * uncertainty * impact / cost).
        self._enqueue_initial_actions()

        # 3. Best-first investigation loop.
        self._investigate()

        # 4. Disagreement resolution round (may add more messages/reassessments).
        self._resolve_disagreements()

        # 5. Risk aggregation.
        findings = self.store.all_findings()
        risk_breakdown = self.risk_engine.compute(findings)
        self.state.risk = risk_breakdown.to_dict()

        # 6. Confidence aggregation (per open/relevant finding, then overall).
        findings_no_info = [f for f in findings if f.severity != Severity.INFO]
        strict_relevant = [f for f in findings if f.severity in (Severity.MEDIUM, Severity.HIGH, Severity.CRITICAL)]
        relevant = strict_relevant if strict_relevant else (findings_no_info or findings)
        confidence_mode = "min" if strict_relevant else "mean"
        breakdowns = []
        for f in relevant:
            ev_items = self.store.evidence_for(f)
            agreement_factor = 0.5 if self.state.unresolved_disagreements else 0.9
            open_qs = sum(1 for q in self.state.open_questions if q.get("related_finding_id") == f.finding_id)
            bd = self.confidence_engine.compute_for_finding(
                f, ev_items, agreement_factor=agreement_factor, open_questions_for_finding=open_qs,
            )
            breakdowns.append(bd)
        overall_confidence = self.confidence_engine.overall(breakdowns, mode=confidence_mode)
        self.state.confidence = {
            "overall": round(overall_confidence, 4),
            "per_finding": {
                f.finding_id: bd.to_dict() for f, bd in zip(relevant, breakdowns)
            },
        }

        evidence_completeness = min(
            1.0, sum(bd.evidence_completeness for bd in breakdowns) / len(breakdowns)
        ) if breakdowns else 0.5

        # 7. Final decision.
        self.decision = self.decision_agent.decide(
            risk=risk_breakdown.overall_risk,
            confidence=overall_confidence,
            critical_override=risk_breakdown.critical_override,
            unresolved_disagreements=self.state.unresolved_disagreements,
            evidence_completeness=evidence_completeness,
            high_impact_change=self.changeset.security_sensitive and self.changeset.database_access
                                and not self.changeset.tests_changed,
        )
        self.bus.publish(AgentMessage(
            sender="decision_agent", type=MessageType.DECISION,
            content=self.decision.outcome, reason="; ".join(self.decision.reasons),
            risk_after=risk_breakdown.overall_risk, confidence_after=overall_confidence,
        ))

        duration = time.time() - t0
        return self._compile_result(duration)

    # ------------------------------------------------------------------
    def _enqueue_initial_actions(self):
        for f in self.store.all_findings():
            # Only findings that represent an actual concern (not a clean
            # "nothing found" result) warrant further investigation -- asking
            # "are there malicious-input tests for this?" only makes sense
            # once Security actually suspects something.
            if f.severity not in (Severity.HIGH, Severity.CRITICAL):
                continue
            uncertainty = 1.0 - f.confidence
            impact = f.risk
            if f.category == "security":
                self.planner.push(InvestigationAction(
                    type=ActionType.REQUEST_EVIDENCE, target_agent="testing_agent",
                    description="Are there tests covering malicious input for this endpoint?",
                    related_finding_id=f.finding_id, severity=f.severity.value,
                    uncertainty=uncertainty, impact=impact,
                ))
                self.planner.push(InvestigationAction(
                    type=ActionType.ASK_QUESTION, target_agent="quality_agent",
                    description="Does the codebase use parameterized queries as a convention?",
                    related_finding_id=f.finding_id, severity=f.severity.value,
                    uncertainty=uncertainty * 0.7, impact=impact * 0.6,
                ))

    def _investigate(self):
        while self.planner.has_next():
            action = self.planner.pop_best()
            self.state.completed_actions.append(action.to_dict())
            self._execute_action(action)

    def _execute_action(self, action: InvestigationAction):
        finding = self.store.get(action.related_finding_id) if action.related_finding_id else None
        if action.type == ActionType.REQUEST_EVIDENCE and finding is not None:
            security = self.agents["security_agent"]
            req = security.request_evidence(
                receiver="testing_agent",
                question="Are there tests covering malicious input for this endpoint?",
                related_finding_id=finding.finding_id, topic="sql_injection",
            )
            resp = self.agents["testing_agent"].handle_message(req)
            if resp is not None:
                no_test_exists = "no malicious-input test" in (resp.content or "").lower()
                if no_test_exists and finding.category == "security":
                    security.reassess(
                        finding,
                        risk=min(1.0, finding.risk + 0.14),
                        confidence=min(1.0, finding.confidence + 0.12),
                        reason="Testing Agent confirmed no malicious-input test exists for this endpoint.",
                    )
                elif not no_test_exists and finding.category == "security":
                    security.reassess(
                        finding,
                        risk=max(0.0, finding.risk - 0.08),
                        confidence=min(1.0, finding.confidence + 0.05),
                        reason="Testing Agent confirmed a malicious-input test exists, slightly reducing risk.",
                    )

        elif action.type == ActionType.ASK_QUESTION and finding is not None:
            quality = self.agents["quality_agent"]
            security = self.agents["security_agent"]
            challenge = quality.challenge(
                receiver="security_agent",
                question="Does the SQL construction use parameterized queries elsewhere in the repository?",
                related_finding_id=finding.finding_id,
            )
            resp = security.handle_message(challenge)
            if resp is not None:
                self.state.open_questions.append({
                    "question": challenge.question, "answer": resp.content,
                    "related_finding_id": finding.finding_id,
                })

    # ------------------------------------------------------------------
    def _resolve_disagreements(self):
        findings = self.store.all_findings()
        disagreements = self.disagreement_engine.detect(findings)
        self.state.disagreements = disagreements
        if not disagreements:
            self.state.unresolved_disagreements = 0
            return

        for d in disagreements:
            self.bus.publish(AgentMessage(
                sender="orchestrator", type=MessageType.DISAGREEMENT,
                content=d.reason, related_finding_id=d.finding_a,
            ))
            fa, fb = self.store.get(d.finding_a), self.store.get(d.finding_b)
            higher, lower = (fa, fb) if fa.risk >= fb.risk else (fb, fa)

            # Ask the higher-risk agent to explain (it answers from its own evidence).
            q1 = AgentMessage(sender="orchestrator", receiver=higher.agent, type=MessageType.QUESTION,
                               question=f"Why does {higher.agent} consider this change {higher.severity.value.lower()} risk?",
                               related_finding_id=higher.finding_id)
            self.bus.publish(q1)
            ev_items = self.store.evidence_for(higher)
            explanation = ev_items[0].description if ev_items else "No further evidence available."
            self.bus.publish(AgentMessage(sender=higher.agent, receiver="orchestrator", type=MessageType.RESPONSE,
                                           content=explanation, related_finding_id=higher.finding_id))

            # Ask the lower-risk agent whether the higher-risk agent's concern
            # actually intersects their own domain.
            q2 = AgentMessage(sender="orchestrator", receiver=lower.agent, type=MessageType.QUESTION,
                               question=f"Does {higher.agent}'s finding affect a {lower.category}-sensitive path?",
                               related_finding_id=lower.finding_id)
            self.bus.publish(q2)

            resolved = False
            if lower.agent == "security_agent" and self.changeset is not None:
                if self.changeset.security_sensitive:
                    self.agents["security_agent"].reassess(
                        lower, risk=min(1.0, lower.risk + 0.25), confidence=min(1.0, lower.confidence + 0.05),
                        reason="Orchestrator investigation confirmed the disputed area is security-sensitive.",
                    )
                    resolved = True
                    self.bus.publish(AgentMessage(sender=lower.agent, receiver="orchestrator",
                                                   type=MessageType.RESPONSE,
                                                   content="Confirmed: the affected path is security-sensitive; raising risk.",
                                                   related_finding_id=lower.finding_id))
                else:
                    self.bus.publish(AgentMessage(sender=lower.agent, receiver="orchestrator",
                                                   type=MessageType.RESPONSE,
                                                   content="No: the affected path is not security-sensitive based on current evidence.",
                                                   related_finding_id=lower.finding_id))

            self.state.open_questions.append({
                "question": q2.question, "resolved": resolved, "related_finding_id": lower.finding_id,
            })

        # Re-check disagreement on the (possibly updated) findings.
        remaining = self.disagreement_engine.detect(self.store.all_findings())
        self.state.disagreements = remaining
        self.state.unresolved_disagreements = len(remaining)
        if remaining:
            self.bus.publish(AgentMessage(
                sender="orchestrator", type=MessageType.ESCALATE,
                content="Agents disagree and available evidence is insufficient to justify autonomous approval.",
            ))

    # ------------------------------------------------------------------
    def _compile_result(self, duration: float) -> dict:
        return {
            "pr_id": self.pr_id,
            "changeset": self.changeset.to_dict(),
            "findings": [f.to_dict() for f in self.store.all_findings()],
            "evidence": [e.to_dict() for e in self.store.evidence.values()],
            "messages": self.bus.to_list(),
            "state": self.state.to_dict(),
            "decision": self.decision.to_dict(),
            "duration_seconds": round(duration, 4),
        }
