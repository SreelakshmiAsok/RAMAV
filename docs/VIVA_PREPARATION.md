# Viva Preparation — RAMAV

Answers are written to be technically defensible, not impressive-sounding.
Where the honest answer is "this is a policy choice, not a scientific
result," it says so.

## Core concepts

**1. What is an agent, in this project?**
Something that perceives part of the environment (a diff, test results, a
Semgrep report) and acts (publishes findings, asks questions, reassesses)
to pursue a shared goal — a trustworthy merge decision. Not every agent is
an LLM; several combine deterministic tools with heuristics, which is
explicit in the spec and in `app/agents/base_agent.py`'s docstring.

**2. Why are multiple agents required instead of one?**
Different concerns need different evidence: security, test coverage, code
quality, dependency risk, performance are not the same question and don't
share a detection method. Separating them lets each be right for the wrong
reasons less often, and lets the system model *disagreement between
concerns* — which a single monolithic tool cannot represent at all.

**3. What makes this "multi-agent" rather than "several tools called in a
loop"?** Real inter-agent messages that change conclusions:
`REQUEST_EVIDENCE` → `RESPONSE` → `REASSESS` actually mutates a Finding's
risk/confidence with an audit trail (`Finding.history`), and this is
asserted by automated tests (`tests/test_scenarios.py`), not just narrated.

**4. What is the difference between an agent and a static-analysis tool?**
A tool (Semgrep, pytest) answers one fixed question about the code. An
agent in this system consumes a tool's output as *evidence*, can be asked
follow-up questions by other agents, and can change its own conclusion when
given new evidence. Semgrep cannot be challenged by the Testing Agent;
the Security Agent can.

**5. How do agents communicate?**
Structured `AgentMessage` objects (`app/coordination/messages.py`) with a
`type` from a fixed vocabulary (TASK/FINDING/QUESTION/REQUEST_EVIDENCE/
RESPONSE/CHALLENGE/DISAGREEMENT/REASSESS/ESCALATE/DECISION), all persisted
to a `MessageBus` and shown verbatim in the dashboard.

**6. How is disagreement detected?**
Pairwise, for findings from different agents that concern the *same file*
(so we're not comparing apples to oranges): a risk-score gap ≥ 0.35 or a
severity-rank gap ≥ 2 is flagged (`app/coordination/disagreement.py`).

**7. What happens if two agents disagree?**
The Orchestrator asks the higher-risk agent to explain, then asks the
lower-risk agent whether the concern intersects their own domain (e.g.
"does the failing test touch a security-sensitive path?"). If the
follow-up doesn't resolve it, the disagreement stays unresolved, which
forces `HUMAN_REVIEW_REQUIRED` regardless of aggregate risk/confidence —
see the next answer.

**8. Why not simply average the risk scores?**
Averaging can hide exactly the case that matters most: one agent
confidently flagging a real problem gets diluted by two agents who didn't
look at that problem at all. `DecisionAgent` checks `unresolved_disagreements
> 0` *before* it even looks at the aggregate risk/confidence numbers — this
is asserted directly by
`tests/test_engines.py::test_disagreement_is_not_simply_averaged_away`.

**9. What is the state of the environment (in AI-agent terms)?**
Partially observable (a vulnerability can exist without any installed tool
detecting it), dynamic (the codebase changes across commits), uncertain
(no evidence is treated as 100% conclusive — hence the Confidence Engine),
sequential (each investigation action can change what's worth doing next),
multi-agent and cooperative (agents share one goal).

**10. What is your search strategy?**
Best-first search over a priority queue (`app/search/investigation.py`):
`priority = severity × uncertainty × impact / cost`. Actions are popped
highest-priority-first, executed (which can create new evidence and
therefore new candidate actions), until the goal condition holds or an
action budget (default 12) is exhausted, at which point the system
escalates rather than looping forever.

**11. Why use confidence at all — why not just risk?**
Risk says "how bad if true"; confidence says "how sure are we it's true
and that we've looked hard enough." A high-risk, low-confidence finding
should not be silently auto-rejected (might be a false positive) OR
auto-approved (might be a real problem nobody checked) — it should go to a
human. Conflating the two loses that distinction.

**12. How is confidence calculated?**
A weighted sum of five factors (agent confidence, evidence strength, tool
reliability, agreement, evidence completeness) minus an uncertainty penalty
proportional to open questions — see `app/confidence/engine.py` for the
exact weights and `docs/ARCHITECTURE.md` for the breakdown shown in the
dashboard.

**13. Are the thresholds (0.30 for auto-approve, 0.85 confidence, etc.)
scientifically optimal?**
No — and the code says so. They are project policy parameters, tunable in
`app/config/settings.py`, not a result of an empirical study. This is
disclosed rather than hidden.

## Tooling / robustness

**14. What happens if Semgrep is unavailable?**
`app/integrations/semgrep_adapter.py` detects this and falls back to a
small deterministic regex/AST scanner, and every Finding/Evidence produced
this way is labeled `HEURISTIC`, never `REAL_TOOL`. In the environment this
project was authored and tested in, Semgrep genuinely is unavailable — the
fallback path is what was actually exercised by the test suite, not a
theoretical branch.

**15. Does the system require an LLM?**
No. All 5 demo scenarios and the entire decision pipeline run and are
tested with zero LLM calls. An LLM is an optional, swappable source of
*explanation text*, never of the decision itself — see the next answer.

**16. What happens if the LLM hallucinates?**
It can, at worst, produce a bad Finding or a bad explanation string. That
Finding still has to clear the deterministic Risk/Confidence/Decision
pipeline, which does not trust any single agent's self-reported confidence
(see `ConfidenceEngine`'s independent weighting of tool reliability and
evidence strength) and can be caught by disagreement detection. The final
`AUTO_APPROVE` / `AUTO_REJECT` / `HUMAN_REVIEW_REQUIRED` call is made by
`DecisionAgent`, a plain deterministic function — never by prompting an LLM
"should I approve this?".

**17. How do you prevent automatic approval when evidence is weak?**
`evidence_completeness` is one of the four required conditions for
`AUTO_APPROVE` (`app/agents/decision_agent.py`); falling short of it forces
`HUMAN_REVIEW_REQUIRED` even when risk and confidence look fine in
isolation.

**18. What happens after a repair? How do you verify it?**
The Repair Agent's patch is never trusted on its own. The *entire* pipeline
(Security, Testing, Quality — real re-scan, real re-run of tests) is
re-executed against a fresh copy of the patched tree, and only if the
originating vulnerability finding is actually gone AND tests still pass is
"Repair verified" reported (`app/services/repair_service.py`). While
building this, the mechanical patch regex initially produced a broken query
(`'?'` instead of `?`) — the revalidation step caught it because the test
suite then failed, which is exactly the scenario this design is meant to
catch.

**19. What is your no-fabrication guarantee?**
Every Finding and Evidence object carries a mandatory `source_type` ∈
{REAL_TOOL, HEURISTIC, LLM_ANALYSIS, MOCK_DEMO}. Tests explicitly assert
this field is always one of the four values
(`tests/test_scenarios.py::TestNoFabrication`), and the dashboard displays
it as a colored badge next to every finding/evidence row.

## Comparisons

**20. How is this different from GitHub code scanning / Dependabot?**
Those are single-purpose detectors. RAMAV's contribution sits one layer up:
it coordinates multiple such detectors, resolves disagreement between them,
and produces one explainable go/no-go decision with a confidence score —
GitHub code scanning does not talk to your test runner or ask it follow-up
questions.

**21. How is this different from SonarQube?**
SonarQube is a quality/maintainability dashboard — it reports metrics, it
does not coordinate agents or make an autonomous merge decision with
disagreement-aware escalation.

**22. How is this different from "an AI code reviewer" (e.g. an LLM
reviewing a diff)?**
An LLM code reviewer is a single (usually stochastic) opinion. RAMAV is
explicitly *not* trying to be a better reviewer — it is a coordination and
decision layer over several independent, mostly-deterministic signals, with
explicit confidence/disagreement handling that a single LLM call has no
mechanism for.

**23. Why not just run Semgrep directly and read the output?**
You could, for security findings alone. You'd get nothing for: "does a test
exist for this," "does this violate repo conventions elsewhere," "should
a human look at this given the evidence is thin," or "these two tools
disagree, now what." Those are exactly RAMAV's contribution.

## Design & limitations

**24. What are your limitations?**
- Fallback analyzers are intentionally simple (a handful of regex rules),
  not a Semgrep replacement
- Disagreement detection is same-file-scoped; cross-file systemic
  disagreement is not modeled
- No live GitHub webhook/token integration in this build (local-clone mode
  only) — see `docs/ENVIRONMENT_NOTES.md` for why
- The evaluation in `evaluation/` is illustrative (5 scenarios), not a
  large labeled dataset — see `docs/RUBRIC_MAPPING.md` and
  `evaluation/README.md` for what would be needed for a real study

**25. How would you scale this system?**
Add a new agent class extending `BaseAgent`, register it in
`Orchestrator.__init__`; nothing else changes (message bus, evidence store,
risk/confidence engines, and dashboard are agent-count-agnostic). Horizontal
scaling of the API is a separate, standard concern (stateless Flask/FastAPI
behind a load balancer, Postgres instead of SQLite) not specific to the
agent design.

**26. How would you evaluate it properly (beyond this classroom demo)?**
A labeled dataset of real PRs with known outcomes (should-have-been-merged /
should-have-been-blocked), computing false-approval and false-rejection
rates against Baseline A (static tools only) and Baseline B (independent
agents, naive averaging) as specified in `evaluation/`. This project does
not claim to have done that at scale — seeded five illustrative scenarios only.

**27. Why file-based matching for disagreement rather than category-based?**
Categories (security vs. performance) are *expected* to often disagree —
that's normal specialization, not conflict. Requiring the same file means
we're only flagging genuine disagreement about the same piece of code.

**28. Why does the disagreement scenario still show a disagreement even
though the SQL-injection scenario's Quality Agent also disagrees with
Security's HIGH severity?**
It can, and when it does, the critical-override check runs *first* in the
Decision Agent, so a confirmed critical vulnerability still forces
AUTO_REJECT even with an unresolved secondary disagreement — the dashboard
will show both facts rather than hiding one.

**29. What did you learn building this that you didn't expect?**
Three real bugs were caught during development, not invented for this
answer: (a) a test file's own explanatory comment containing the word
"malicious" tricked the naive keyword search into believing a
malicious-input test existed when it didn't; (b) the Repair Agent's regex
initially left the SQL placeholder inside quotes (`'?'`), producing a
syntactically-valid but semantically-broken parameterized query, caught
only because the revalidation step re-ran the real test suite; (c) an
overly broad disagreement rule initially flagged spurious disagreement
between unrelated findings until file-scoping was added. All three are
documented in the commit history / this file rather than smoothed over.

**30. Why Flask instead of the specified FastAPI?**
Purely an environment constraint (no network access to `pip install
fastapi` while building this) — documented candidly in
`docs/ENVIRONMENT_NOTES.md`, with the porting path spelled out. The route
shapes and JSON contracts were designed to make that port mechanical.

**31. Is the frontend actually verified working?**
The backend/API it calls is fully tested end-to-end over real HTTP. The
browser rendering itself could not be verified in the authoring sandbox
(no network to fetch the CDN-hosted React/font files) — this is disclosed
rather than assumed, and is the one part of the deliverable to double-check
first when demoing on a normal internet-connected laptop.
