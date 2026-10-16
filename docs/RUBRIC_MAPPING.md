# Rubric Mapping — RAMAV

## Review 1

### PEAS Formulation — 3 marks
- `docs/peas.json` — structured PEAS data, single source of truth
- Dashboard "PEAS & Architecture" tab renders it live from `GET /api/system/peas`
- See also this document's own copy below for the report/viva

### Environment & Agent Analysis — 3 marks
- Environment classification: **partially observable** (tools can be
  unavailable; a vulnerability can exist without being detected), **dynamic**
  (the codebase changes between commits), **uncertain** (confidence is
  explicitly modeled because evidence is never 100% conclusive),
  **sequential** (investigation actions build on prior evidence),
  **multi-agent, cooperative** (agents share one goal — a trustworthy
  decision — even though they specialize)
- Agent roles and *why each exists*: see the table in `docs/VIVA_PREPARATION.md`
  ("Why are multiple agents required?")
- Communication protocol: `app/coordination/messages.py` — 10 message types,
  fully implemented and exercised (see `tests/test_scenarios.py`, which
  asserts `REQUEST_EVIDENCE` / `RESPONSE` / `REASSESS` / `CHALLENGE` /
  `DISAGREEMENT` / `ESCALATE` messages actually appear in a real run)

### Algorithmic Modeling & Search Strategy — 3 marks
- State representation: `OrchestratorState` (`app/agents/orchestrator.py`)
- Action representation: `InvestigationAction` (`app/search/investigation.py`)
- Goal condition: evidence sufficient AND confidence high enough AND no
  unresolved critical finding AND no unresolved disagreement (implemented
  across `RiskEngine` / `ConfidenceEngine` / `DecisionAgent`, not just
  described)
- Cost: `DEFAULT_COST` per action type
- Heuristic / priority: `priority(action) = severity × uncertainty × impact / cost`
- Search strategy: best-first search over a `heapq` priority queue
  (`InvestigationPlanner`), with an explicit action budget and escalation on
  exhaustion
- Dashboard "Investigation Trace" tab shows the *actual* actions executed,
  in priority order, for the run just performed — not a canned diagram

### Q&A & Presentation Mechanics — 1 mark
- `docs/VIVA_PREPARATION.md` — 30+ questions with technically accurate answers
- `docs/LIVE_DEMO_SCRIPT.md` — a rehearsed walkthrough

## Review 2

### Tool/Package Selection & Setup — 3 marks
- `docs/TOOL_SELECTION.md` — every technology, what it does, why chosen,
  the alternative considered, install instructions
- `docs/SEMGREP_GUIDE.md` — dedicated Semgrep explanation as required
- `docs/ENVIRONMENT_NOTES.md` — full honesty about what had to be
  substituted in the authoring sandbox (no network access) and why, plus
  exactly what changes with real internet access

### Multi-Agent Execution & Interaction — 3 marks
This is the rubric item the spec is most insistent about, and the one most
directly falsifiable. Concretely:
- `tests/test_scenarios.py::TestSqlInjectionScenario` asserts, against a
  REAL run of the pipeline (not a mock), that:
  - `REQUEST_EVIDENCE`, `RESPONSE`, and `REASSESS` messages actually appear
  - The Security Agent's finding carries a non-empty reassessment history
  - The Quality Agent actually sent a `CHALLENGE` to the Security Agent
- `tests/test_scenarios.py::TestDisagreementScenario` asserts a real
  `DISAGREEMENT` and `ESCALATE` message appear, and that the triggering
  Testing Agent finding is backed by a REAL_TOOL test run (not a fixture)
- The dashboard's "Agent Conversation" tab renders this exact message list,
  live, for whichever scenario was just run

### Demo Quality & Testing Scenarios — 3 marks
- 5 demo scenarios, each a real 2-commit git repository:
  Safe / SQL Injection / Disagreement / Repair+Revalidate / Low Evidence
- `docs/LIVE_DEMO_SCRIPT.md` gives the exact click-through sequence
- Every scenario's outcome is asserted by an automated test, not just
  eyeballed once during development

### Code Structure & Scalability — 1 mark
- Adding a new agent (e.g. a Documentation or Compliance Agent) requires:
  1. A new class extending `BaseAgent` implementing `analyze()`
  2. One line registering it in `Orchestrator.__init__`'s `self.agents` dict
  3. Nothing else — the message bus, evidence store, risk/confidence
     engines and dashboard are all agent-count-agnostic
- See `docs/VIVA_PREPARATION.md`, "How would you scale this system?"
