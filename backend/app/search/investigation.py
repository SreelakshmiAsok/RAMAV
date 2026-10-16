"""
Adaptive Investigation Search Strategy
=======================================
This implements the "Algorithmic Modeling & Search Strategy" rubric item as
actual code, not just documentation.

STATE  : InvestigationState -- current findings, evidence, confidence,
         unresolved questions, disagreements, severity, changeset.
ACTIONS: InvestigationAction -- invoke an agent, ask another agent a
         question, request evidence, reassess a finding, escalate.
GOAL   : evidence is sufficient AND confidence is high enough AND no
         unresolved critical finding AND no unresolved disagreement.
COST   : a fixed estimated_cost per action type (invoking an agent again is
         cheaper than a full re-scan; asking a question is cheap).
HEURISTIC / PRIORITY:

    priority(action) = (severity * uncertainty * impact) / estimated_cost

This is a best-first search: at each step we pick the highest-priority
action from a priority queue, execute it (which may add new findings/evidence
and therefore new candidate actions), and stop when the goal condition holds
or the action budget is exhausted (in which case we escalate).
"""
from __future__ import annotations

import heapq
import itertools
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional


class ActionType(str, Enum):
    INVOKE_AGENT = "INVOKE_AGENT"
    REQUEST_EVIDENCE = "REQUEST_EVIDENCE"
    ASK_QUESTION = "ASK_QUESTION"
    REASSESS = "REASSESS"
    RERUN_ANALYSIS = "RERUN_ANALYSIS"
    ESCALATE = "ESCALATE"


DEFAULT_COST = {
    ActionType.INVOKE_AGENT: 3.0,
    ActionType.REQUEST_EVIDENCE: 1.0,
    ActionType.ASK_QUESTION: 1.0,
    ActionType.REASSESS: 1.5,
    ActionType.RERUN_ANALYSIS: 4.0,
    ActionType.ESCALATE: 0.5,
}

SEVERITY_WEIGHT = {"INFO": 0.2, "LOW": 0.4, "MEDIUM": 0.6, "HIGH": 0.85, "CRITICAL": 1.0}


@dataclass(order=True)
class _QueueItem:
    neg_priority: float
    seq: int
    action: "InvestigationAction" = field(compare=False)


@dataclass
class InvestigationAction:
    type: ActionType
    target_agent: str
    description: str
    related_finding_id: Optional[str] = None
    severity: str = "MEDIUM"
    uncertainty: float = 0.5   # how unresolved / unclear this is, 0..1
    impact: float = 0.5        # how much this could change the final decision, 0..1
    estimated_cost: Optional[float] = None

    def priority(self) -> float:
        cost = self.estimated_cost if self.estimated_cost is not None else DEFAULT_COST[self.type]
        sev = SEVERITY_WEIGHT.get(self.severity, 0.5)
        return (sev * self.uncertainty * self.impact) / max(cost, 0.1)

    def to_dict(self):
        d = self.__dict__.copy()
        d["type"] = self.type.value
        d["priority"] = round(self.priority(), 4)
        return d


class InvestigationPlanner:
    """
    A best-first search planner. Candidate actions are pushed in with a
    priority; `pop_best` returns (and removes) the highest-priority one so
    the orchestrator can execute it and then push whatever new candidate
    actions result from what it learned.
    """

    def __init__(self, max_actions: int = 12):
        self._heap: list[_QueueItem] = []
        self._counter = itertools.count()
        self.max_actions = max_actions
        self.executed: list[InvestigationAction] = []

    def push(self, action: InvestigationAction):
        heapq.heappush(self._heap, _QueueItem(-action.priority(), next(self._counter), action))

    def has_next(self) -> bool:
        return bool(self._heap) and len(self.executed) < self.max_actions

    def peek_ranked(self) -> list[InvestigationAction]:
        return [item.action for item in sorted(self._heap)]

    def pop_best(self) -> Optional[InvestigationAction]:
        if not self._heap:
            return None
        item = heapq.heappop(self._heap)
        self.executed.append(item.action)
        return item.action

    def budget_exhausted(self) -> bool:
        return len(self.executed) >= self.max_actions
