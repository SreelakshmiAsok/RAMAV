"""
BaseAgent
=========
Common interface every specialized agent implements. An agent is NOT
required to be an LLM -- most of ours combine deterministic tools (Semgrep,
pytest, AST inspection) with heuristics, and only optionally call a local
LLM for explanation text. This is intentional: it is more reliable and more
defensible academically (see docs/VIVA_PREPARATION.md, "Does the system
require an LLM?").
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.analysis.change_analyzer import ChangeSet
from app.coordination.messages import AgentMessage, MessageBus, MessageType, Priority
from app.evidence.store import EvidenceStore, Finding, Evidence


class BaseAgent(ABC):
    name: str = "base_agent"
    category: str = "generic"

    def __init__(self, bus: MessageBus, store: EvidenceStore, repo_path: str):
        self.bus = bus
        self.store = store
        self.repo_path = repo_path

    # ---- lifecycle -----------------------------------------------------
    @abstractmethod
    def analyze(self, changeset: ChangeSet) -> list[Finding]:
        """Run this agent's analysis and return newly created Findings."""
        raise NotImplementedError

    def handle_message(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Default handling for REQUEST_EVIDENCE / CHALLENGE / QUESTION messages
        sent to this agent. Subclasses override to answer meaningfully."""
        return None

    def request_evidence(self, receiver: str, question: str, related_finding_id: str = None,
                          priority: Priority = Priority.HIGH, topic: str = None) -> AgentMessage:
        msg = AgentMessage(
            sender=self.name, receiver=receiver, type=MessageType.REQUEST_EVIDENCE,
            question=question, related_finding_id=related_finding_id, priority=priority, topic=topic,
        )
        return self.bus.publish(msg)

    def challenge(self, receiver: str, question: str, related_finding_id: str = None) -> AgentMessage:
        msg = AgentMessage(
            sender=self.name, receiver=receiver, type=MessageType.CHALLENGE,
            question=question, related_finding_id=related_finding_id, priority=Priority.HIGH,
        )
        return self.bus.publish(msg)

    def respond(self, receiver: str, content: str, related_finding_id: str = None,
                related_evidence_ids: list[str] = None) -> AgentMessage:
        msg = AgentMessage(
            sender=self.name, receiver=receiver, type=MessageType.RESPONSE,
            content=content, related_finding_id=related_finding_id,
            related_evidence_ids=related_evidence_ids or [],
        )
        return self.bus.publish(msg)

    def reassess(self, finding: Finding, *, risk: float = None, confidence: float = None,
                 reason: str = "") -> AgentMessage:
        before_r, before_c = finding.risk, finding.confidence
        finding.reassess(risk=risk, confidence=confidence, reason=reason)
        msg = AgentMessage(
            sender=self.name, type=MessageType.REASSESS,
            related_finding_id=finding.finding_id, reason=reason,
            risk_before=before_r, risk_after=finding.risk,
            confidence_before=before_c, confidence_after=finding.confidence,
        )
        return self.bus.publish(msg)

    def publish_finding(self, finding: Finding) -> AgentMessage:
        self.store.add_finding(finding)
        msg = AgentMessage(
            sender=self.name, type=MessageType.FINDING,
            related_finding_id=finding.finding_id,
            content=finding.title,
            confidence_after=finding.confidence, risk_after=finding.risk,
        )
        return self.bus.publish(msg)
