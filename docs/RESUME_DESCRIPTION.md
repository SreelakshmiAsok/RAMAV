# Resume Description — RAMAV

## One-line bullet
Built a multi-agent pre-merge validation system where specialized agents
exchange evidence and challenge each other's findings, with disagreement
detection and confidence-aware decision-making replacing naive score
averaging.

## Two-bullet version
- Designed and implemented a coordination layer over five specialized
  code-analysis agents (security, testing, quality, dependency,
  performance) that communicate via a structured message protocol
  (evidence requests, challenges, reassessments) rather than running
  independently.
- Implemented an explainable risk/confidence/decision pipeline with
  disagreement detection and a best-first investigation search, achieving
  closed-loop repair verification (a generated patch is only accepted after
  the full pipeline re-confirms the vulnerability is resolved).

## Detailed project description
RAMAV (Risk-Aware Multi-Agent Automated Validation) is a research-oriented
system that investigates whether specialized software-analysis agents can
collaboratively gather and evaluate evidence about a code change — while
explicitly accounting for confidence and disagreement — to decide when an
automated pre-merge decision is trustworthy.

Five agents (security, testing, quality, dependency, performance) each
combine deterministic tooling (Semgrep, test execution, AST analysis) with
heuristics, and communicate through a typed message protocol (TASK,
FINDING, QUESTION, REQUEST_EVIDENCE, RESPONSE, CHALLENGE, DISAGREEMENT,
REASSESS, ESCALATE, DECISION). An Orchestrator maintains explicit
coordination state and runs a best-first investigation search
(`priority = severity × uncertainty × impact / cost`) to decide what to
investigate next, rather than invoking every agent once and stopping.

A Disagreement Engine detects when agents reach conflicting conclusions
about the same code and forces human escalation rather than averaging the
scores away. A Confidence Engine computes an explainable, component-broken
confidence score (agent confidence, evidence strength, tool reliability,
agreement, evidence completeness) instead of asking an LLM to self-report
certainty. A deterministic Decision Agent — never an LLM — makes the final
AUTO_APPROVE / AUTO_REJECT / HUMAN_REVIEW_REQUIRED call.

A Repair Agent can propose a mechanical patch for a detected vulnerability,
but the patch is never trusted on its own: the full multi-agent pipeline
re-runs against the patched code, including re-executing the test suite,
before a repair is reported as verified.

Every finding and evidence item is tagged with its provenance (REAL_TOOL /
HEURISTIC / LLM_ANALYSIS / MOCK_DEMO) to prevent silently presenting
fallback heuristics as authoritative tool output. The system includes an
interactive dashboard (React) showing the live agent conversation, risk and
confidence breakdowns, and the investigation search trace, backed by 35
automated tests exercising real demo repositories (built as actual 2-commit
git histories) rather than mocked fixtures.
