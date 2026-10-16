# RAMAV — Risk-Aware Multi-Agent Automated Validation

A pre-merge validation system where specialized agents (security, testing,
quality, dependency, performance) **exchange messages, challenge each
other's findings, reassess, and escalate to humans when they disagree or
evidence is thin**. The contribution is the coordination and decision
layer, not another detector.

> **Read `docs/ENVIRONMENT_NOTES.md` first.** It lists what differs from the
> original spec (Flask instead of FastAPI, sqlite3, CDN React with no build
> step, unittest) and exactly what was and was NOT verified.

## Quick start

Prerequisites: Python 3.10+, git. Internet is needed only for the
dashboard's CDN scripts (React, fonts).

```bash
# Linux / macOS
bash scripts/start_demo.sh
# Windows
scripts\start_demo.bat
```

Open http://localhost:8000 → **Demo Scenarios** → click **SQL INJECTION PR**
→ view **Agent Conversation**, **Findings & Evidence**, **Investigation
Trace**, **Risk & Decision**.

Manual: `pip install -r backend/requirements.txt && python3 scripts/setup_demo_repos.py && cd backend && python3 -m app.main`

## Tests and evaluation

```bash
bash scripts/run_tests.sh              # 35 tests (unittest; pytest if installed)
python3 evaluation/run_evaluation.py   # 3-method comparison (see caveats)
```

## Optional tools

- **Semgrep:** `pip install semgrep` — auto-detected; otherwise a labeled
  HEURISTIC fallback runs (see `docs/SEMGREP_GUIDE.md`).
- **Ollama:** `OLLAMA_BASE_URL`/`OLLAMA_MODEL` in `.env.example`. Currently
  only checked on the System Health page; no LLM calls are made in this
  build, and the decision policy never depends on an LLM.
- **PostgreSQL:** not used; SQLite (`ramav.db`) is the store.
- **GitHub:** local-clone analysis only (`POST /api/analyze/pr` with
  `local_clone_path`). No live GitHub API/webhook/comment posting.

## Scenarios

| Button | Real outcome |
|---|---|
| Safe PR | AUTO_APPROVE |
| SQL Injection PR | AUTO_REJECT (REQUEST_EVIDENCE → RESPONSE → REASSESS, Quality CHALLENGE) |
| Agent Disagreement | HUMAN_REVIEW_REQUIRED (real failing test vs clean scans) |
| Repair + Revalidate | pre: AUTO_REJECT; post-repair full re-run; "Repair verified" only if finding gone and tests pass |
| Missing Tool / Low Evidence | HUMAN_REVIEW_REQUIRED |

## Understanding the output

- **Risk:** weighted per-category max (weights in `app/risk/engine.py`), with a critical-finding override.
- **Confidence:** explainable weighted factors (`app/confidence/engine.py`).
- **Decision:** deterministic policy (`app/agents/decision_agent.py`); thresholds are project policy, not scientifically tuned.
- **Source badges:** REAL_TOOL / HEURISTIC / LLM_ANALYSIS / MOCK_DEMO on every finding.

## Known limitations

- Fallback analyzers are simple regex/AST rules.
- Demo scenarios are small, and thresholds were tuned against them.
- Not built: WebSockets/SSE live streaming (results appear when a run finishes), OpenTelemetry, frontend tests, separate pages for Confidence/Evidence Explorer/Evaluation/"Why Coordination" (merged into tabs), analysis replay, LangGraph.
- Dashboard rendering and Docker files are unverified (see ENVIRONMENT_NOTES).

## Docs

`docs/ARCHITECTURE.md`, `RUBRIC_MAPPING.md`, `VIVA_PREPARATION.md`, `TOOL_SELECTION.md`, `SEMGREP_GUIDE.md`, `LIVE_DEMO_SCRIPT.md`, `RESUME_DESCRIPTION.md`, `peas.json`.
