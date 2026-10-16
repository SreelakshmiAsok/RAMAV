# Semgrep Guide — RAMAV

## What Semgrep is

Semgrep is a static analysis tool that scans source code against a library
of pattern-based rules ("if you see code shaped like *this*, flag it") for
security bugs, correctness bugs, and code-quality issues. It supports many
languages and ships both official and community rule sets.

## Why we use it

It is the industry-standard, freely-available way to get real, reputable
security findings without writing a detector from scratch. Using it (when
available) means the Security Agent's HIGH-severity findings are backed by
a widely-trusted tool, not just our own regex guesses.

## What it actually scans

Source files matching the languages in its rule pack — for this project,
Python. It does **not** run the code, execute tests, or understand runtime
behavior; it pattern-matches source structure (an AST-aware pattern
matcher, not a plain string grep, though string/regex-like patterns are
also supported).

## How rules work

A rule is a small YAML pattern plus metadata (severity, message, references).
Example (simplified) rule for exactly the vulnerability class in this
project's demo:

```yaml
rules:
  - id: python-sql-injection-fstring
    languages: [python]
    severity: ERROR
    message: >
      Detected a SQL query built with an f-string. This could lead to SQL
      injection if any part of the string is user-controlled. Use a
      parameterized query instead.
    patterns:
      - pattern: $CURSOR.execute(f"...")
```

## How results are obtained

```bash
semgrep scan --config auto .
```

`--config auto` picks a broad, general-purpose rule pack automatically.
`--json` (used internally by `app/integrations/semgrep_adapter.py`) returns
machine-readable output:

```json
{
  "results": [
    {
      "check_id": "python-sql-injection-fstring",
      "path": "app/routes/user.py",
      "start": {"line": 15},
      "extra": {
        "message": "Detected a SQL query built with an f-string...",
        "severity": "ERROR"
      }
    }
  ]
}
```

## How the Security Agent consumes the results

`app/integrations/semgrep_adapter.py::run_semgrep()` parses this JSON into
`SemgrepFinding` objects; `app/agents/security_agent.py` turns each one into
an `Evidence` (tagged `REAL_TOOL`, tool=`"semgrep"`) and a `Finding` with a
severity/risk mapping. Nothing about the message or line number is
invented — it is copied straight from Semgrep's own output.

## How Semgrep differs from our agent system

**Semgrep ≠ Multi-Agent System.** Semgrep answers exactly one question:
"does this code match a known-bad pattern?" It cannot be asked a follow-up
question, cannot look at test coverage, cannot compare its conclusion
against another tool's and decide who's more likely right, and has no
concept of "confidence" or "human review." RAMAV's Security Agent uses
Semgrep as one *evidence source*; the coordination (asking Testing Agent
"is there a test for this?", asking Quality Agent about repo conventions,
detecting disagreement, computing confidence, deciding to escalate) is all
RAMAV, not Semgrep.

## What happens when Semgrep is unavailable

`semgrep_available()` checks `shutil.which("semgrep")`. If it's missing (as
in the sandbox this project was built in — see `docs/ENVIRONMENT_NOTES.md`),
`run_semgrep()` transparently falls back to a small deterministic
regex/AST scanner (`_fallback_scan` in the same file) that catches the
specific vulnerability classes used in the demo scenarios (SQL injection via
string formatting/concatenation, hardcoded secrets, `eval`/`exec`). Every
Finding/Evidence produced this way is labeled `HEURISTIC`, not `REAL_TOOL` —
the dashboard shows this distinction as a colored badge, and
`tests/test_semgrep_adapter.py` asserts the fallback both catches the known
vulnerable pattern and does not flag clean code.

## Example output (from this project's own fallback scan)

```
rule_id: sql-injection-fstring
severity: HIGH
file: app/routes/user.py
line: 12
message: Possible SQL injection: f-string interpolated directly into a SQL query.
metadata: {"engine": "ramav-fallback-heuristic"}
```

## How to demonstrate it live

1. Show `GET /api/system/tools` on the System Health dashboard page — it
   will honestly say whether Semgrep is installed on the demo machine.
2. If Semgrep **is** installed on the demo laptop (`pip install semgrep`
   beforehand), click "SQL INJECTION PR" and the Findings tab will show
   `source_type: REAL_TOOL, tool: semgrep`.
3. If it is **not** installed, the same button still works — the Findings
   tab will show `source_type: HEURISTIC, tool: ramav-fallback-heuristic`,
   and the System Health page explains why.
4. Either way, run `semgrep scan --config auto demo-repository/scenarios/sql_injection`
   manually in a terminal to show the raw tool output side-by-side with
   what the dashboard displays, to make the "Semgrep provides evidence, the
   agent system coordinates it" point concrete.
