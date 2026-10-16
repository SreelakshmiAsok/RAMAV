# Live Demo Script — RAMAV (5–10 minutes)

Run `scripts/start_demo.sh` (or `start_demo.bat` on Windows) beforehand and
confirm `http://localhost:8000` loads before the teacher arrives.

## Step 1 — Open the dashboard
Navigate to `http://localhost:8000`. Point out the sidebar: this is a
coordination dashboard, not a static-analysis report.

## Step 2 — Show System Health
Click **System Health**. Say plainly which real tools are available on
*this* machine (Semgrep / git / etc.) — this sets honest expectations for
what "REAL_TOOL" vs "HEURISTIC" will mean in the findings you're about to
show.

## Step 3 — Show PEAS & Architecture
Click **PEAS & Architecture**. Point at the "Why Coordination?" panel —
this pre-empts the single most common question ("isn't this just Semgrep?").

## Step 4 — Run the Safe PR
Go to **Demo Scenarios**, click **SAFE PR**. Switch to **Overview** — show
AUTO_APPROVE, low risk, high confidence, all agents "completed" with clean
findings.

## Step 5 — Run the SQL Injection PR
Click **SQL INJECTION PR**. Then:
1. **Findings & Evidence** tab — point at the Security Agent's HIGH finding,
   `source_type` badge, and the file/line it points to.
2. **Agent Conversation** tab — scroll to the `REQUEST_EVIDENCE` message
   from Security → Testing, the `RESPONSE` ("no malicious-input test
   exists"), the `REASSESS` message showing risk climbing, and the
   `CHALLENGE` from Quality → Security about parameterized-query
   conventions.
3. **Investigation Trace** tab — show the priority-ranked actions that were
   actually executed, not a fixed script.
4. **Risk & Decision** tab — show the risk breakdown bars, the critical
   override banner, and the final AUTO_REJECT with its stated reasons.

## Step 6 — Run the Disagreement scenario
Click **AGENT DISAGREEMENT**. Go to **Risk & Decision** — show the
Testing Agent's real failing-test finding (point out `source_type:
REAL_TOOL`) conflicting with Security/Quality's clean scans, the
disagreement description naming both agents, and the resulting
HUMAN_REVIEW_REQUIRED with "agents disagree" as the stated reason. This is
the strongest single screen for the "not just averaging" argument.

## Step 7 — Run the Repair + Revalidate scenario
Click **REPAIR + REVALIDATE**. Go to the **Repair + Revalidation** tab —
show the pre-repair AUTO_REJECT, the patch log (the actual code diff
description), and the post-repair decision. Say explicitly: "the patch
being generated is not what earns 'verified' — the full pipeline had to
re-run and find nothing, including re-running the test suite."

## Step 8 — (optional) Missing Tool / Low Evidence
Click **MISSING TOOL / LOW EVIDENCE**. Show HUMAN_REVIEW_REQUIRED driven
purely by low confidence (no test runner available for this language),
distinguishing "the system doesn't know" from "the system knows it's bad."

## Step 9 — Rubric mapping
Briefly show `docs/RUBRIC_MAPPING.md` open in an editor tab if there's time,
or simply state the four Review-2 rubric items and point back at what was
just demoed for each.

## If something goes wrong on stage
- Server not starting: check the terminal for a Python traceback — the
  most common cause is a stale `ramav.db` lock; delete it and restart.
- A demo button seems to hang: each button re-runs the FULL pipeline
  including a real git diff and (if installed) a real Semgrep scan, so a
  few seconds' delay on first click is expected, not a bug.
- Dashboard shows nothing / blank page: confirm internet access — the
  dashboard loads React from a CDN and was not build-verified on a
  fully offline machine (see `docs/ENVIRONMENT_NOTES.md`).
