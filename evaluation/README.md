# Evaluation Framework — RAMAV

This is a small, honest evaluation harness, not a large empirical study. It
runs the three methods described in "Why Coordination?" against the five
bundled demo scenarios and reports what actually happened — it does not
claim statistically significant results from five data points, and the
runner's output says so.

## Dataset format

`dataset.json` lists each scenario with its **expected** qualitative
outcome (defined by the scenario's own design intent, not by running the
system and copying its answer):

```json
{
  "scenario": "sql_injection",
  "path": "demo-repository/scenarios/sql_injection",
  "expected_outcome": "AUTO_REJECT",
  "notes": "Introduces an f-string SQL injection with no malicious-input test."
}
```

## Baselines compared

- **Baseline A — static tools only**: run the Security Agent's Semgrep/
  fallback scan in isolation; decision = REJECT if any HIGH/CRITICAL
  finding, else APPROVE. No testing/quality/dependency signal, no
  disagreement handling.
- **Baseline B — independent agents, naive aggregation**: run all five
  agents independently (no inter-agent messages), average their risk
  scores, threshold the average. This is the "collection of tools" anti-
  pattern the project spec explicitly warns against.
- **Proposed — RAMAV**: the full coordinated pipeline (this repository).

## Metrics

- Agreement with expected outcome (exact match / directionally correct /
  wrong)
- Whether disagreement was detected when the scenario was designed to
  contain it (disagreement scenario only)
- Whether a critical vulnerability was ever auto-approved (should never
  happen for any method on the SQL injection scenario)

## Running it

```bash
python3 evaluation/run_evaluation.py
```

Writes `evaluation/results.json` and prints a summary table. Re-run any
time the demo scenarios or engines change — the numbers are always
regenerated, never hand-edited.

## What real evaluation would need (not done here)

A labeled dataset of real historical PRs (tens to hundreds, ideally from
public repositories with known outcomes — reverted vs. merged-and-stable),
computing false-approval and false-rejection rates with confidence
intervals, and comparing against the same three methods. This is called
out explicitly as future work in `docs/VIVA_PREPARATION.md`, Q26.

## Measured results and an important caveat

`python3 evaluation/run_evaluation.py` produced (5 scenarios): static-only
3/5 exact match (2 unsafe auto-approvals), naive-average 1/5 (4 unsafe
auto-approvals), RAMAV 5/5 (0 unsafe auto-approvals).

**Circularity warning:** the scenarios, their expected outcomes, and RAMAV's
thresholds/heuristics were all written and tuned by the same author during
development (e.g. the safe scenario's confidence was tuned until it cleared
the approval threshold). RAMAV matching 5/5 therefore demonstrates that the
pipeline behaves as designed, NOT that it generalises. The baselines are
also simple implementations chosen by the author. Do not present these
numbers as evidence of real-world accuracy; a held-out set of real PRs is
required for that.
