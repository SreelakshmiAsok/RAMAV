"""
Agent Communication Protocol
=============================
Every interaction between agents in RAMAV is represented as a structured
Message object. This is the backbone of "actual multi-agent coordination":
agents do not just return a value to a caller, they exchange typed messages
that get stored, displayed in the dashboard, and used to drive the
orchestrator's investigation loop.

We deliberately avoid a heavyweight validation framework here (no network
access to install pydantic in the build sandbox) and instead use plain
dataclasses with a small amount of hand-rolled validation. Swapping this for
pydantic BaseModel classes later is a mechanical, low-risk change -- the
field names and semantics are the same.
"""
from __future__ import annotations

import itertools
import time
import uuid
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Optional


class MessageType(str, Enum):
    TASK = "TASK"
    FINDING = "FINDING"
    QUESTION = "QUESTION"
    REQUEST_EVIDENCE = "REQUEST_EVIDENCE"
    RESPONSE = "RESPONSE"
    CHALLENGE = "CHALLENGE"
    DISAGREEMENT = "DISAGREEMENT"
    REASSESS = "REASSESS"
    ESCALATE = "ESCALATE"
    DECISION = "DECISION"


class Priority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


_counter = itertools.count(1)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{next(_counter):05d}-{uuid.uuid4().hex[:6]}"


@dataclass
class AgentMessage:
    """A single unit of agent-to-agent (or agent-to-orchestrator) communication."""

    sender: str
    type: "MessageType"
    receiver: Optional[str] = None
    topic: Optional[str] = None
    question: Optional[str] = None
    content: Optional[str] = None
    related_finding_id: Optional[str] = None
    related_evidence_ids: list[str] = field(default_factory=list)
    priority: "Priority" = Priority.MEDIUM
    confidence_before: Optional[float] = None
    confidence_after: Optional[float] = None
    risk_before: Optional[float] = None
    risk_after: Optional[float] = None
    reason: Optional[str] = None
    payload: dict[str, Any] = field(default_factory=dict)

    message_id: str = field(default_factory=lambda: _new_id("MSG"))
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["type"] = self.type.value if isinstance(self.type, MessageType) else self.type
        d["priority"] = self.priority.value if isinstance(self.priority, Priority) else self.priority
        return d


class MessageBus:
    """
    Stores the complete conversation between agents for a single analysis run.
    This is what powers the "Agent Conversation" page in the dashboard, and
    is also what the orchestrator's disagreement/search logic reads back over
    to decide what to do next -- it is genuinely used for coordination, not
    just a log.
    """

    def __init__(self):
        self._messages: list[AgentMessage] = []

    def publish(self, message: AgentMessage) -> AgentMessage:
        self._messages.append(message)
        return message

    def all(self) -> list[AgentMessage]:
        return list(self._messages)

    def by_type(self, mtype: MessageType) -> list[AgentMessage]:
        return [m for m in self._messages if m.type == mtype]

    def between(self, a: str, b: str) -> list[AgentMessage]:
        return [
            m for m in self._messages
            if (m.sender == a and m.receiver == b) or (m.sender == b and m.receiver == a)
        ]

    def to_list(self) -> list[dict]:
        return [m.to_dict() for m in self._messages]
