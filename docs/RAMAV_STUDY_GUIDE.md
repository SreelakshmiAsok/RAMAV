# RAMAV Comprehensive Study & Architecture Guide
**Risk-Aware Multi-Agent Automated Validation**

---

## 1. What is RAMAV? (Executive Summary)

**RAMAV** is an intelligent, pre-merge software validation system designed to autonomously inspect pull requests, challenge code safety, coordinate specialized AI agents, and decide whether a code change is safe to merge into production.

### The Problem It Solves
Traditional CI/CD pipelines rely on isolated static analysis tools (linters, SAST scanners like SonarQube or standard Semgrep):
1. **Isolated Scanners Lack Context:** A security scanner flags a potential vulnerability, but has no idea if the test suite actually exercises that code path or if mock data is used.
2. **Notification Fatigue & False Positives:** Developers are flooded with hundreds of warnings without prioritization.
3. **Naive LLMs Hallucinate:** Simply passing a code diff to a generic Large Language Model (e.g., ChatGPT) results in non-deterministic answers, hallucinations, and unverified fixes that cannot be trusted for mission-critical merge gates.

### The RAMAV Breakthrough
RAMAV is a **coordination and decision layer**, not just another scanner:
- Specialized agents (Security, Testing, Quality, Dependencies, Performance) **talk to each other**.
- Agents **exchange messages**, **request evidence**, **challenge assumptions**, and **reassess their risk scores**.
- If a vulnerability is found, an automated **Repair Agent** proposes a fix, but that fix is **never trusted on blind faith**—the entire multi-agent pipeline re-validates the patched code in a closed loop before approval.
- Decisions are governed by an **explainable, deterministic policy** rather than random LLM whims.

---

## 2. High-Level Architecture

RAMAV operates in three distinct conceptual layers:

```
┌────────────────────────────────────────────────────────────────────────┐
│                        1. INGESTION LAYER                              │
│   GitHub Pull Request / Local Git Commits  ───>  Change Analyzer       │
│   (Diffs, AST Parsing, Language Detection, Touchpoint Identification)  │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   2. MULTI-AGENT COORDINATION LAYER                    │
│                                                                        │
│   ┌───────────────────┐    MessageBus     ┌───────────────────┐        │
│   │   SecurityAgent   │◄─────────────────►│   TestingAgent    │        │
│   │ (Semgrep AST Scan)│ (REQUEST_EVIDENCE)│ (Pytest/Unittest) │        │
│   └─────────┬─────────┘                   └─────────┬─────────┘        │
│             │                                       │                  │
│             ▼                                       ▼                  │
│   ┌───────────────────┐                   ┌───────────────────┐        │
│   │   QualityAgent    │◄─────────────────►│  DependencyAgent  │        │
│   │ (Python AST Rules)│    (CHALLENGE)    │  (Manifest Check) │        │
│   └─────────┬─────────┘                   └─────────┬─────────┘        │
│             │                                       │                  │
│             └───────────────────┬───────────────────┘                  │
│                                 ▼                                      │
│                     ┌───────────────────────┐                          │
│                     │   PerformanceAgent    │                          │
│                     │  (Algorithmic Loops)  │                          │
│                     └───────────────────────┘                          │
│                                 │                                      │
│                                 ▼                                      │
│                     ┌───────────────────────┐                          │
│                     │     Orchestrator      │                          │
│                     │ (Investigation Search)│                          │
│                     └───────────────────────┘                          │
└──────────────────────────────────┬─────────────────────────────────────┘
                                   │
                                   ▼
┌────────────────────────────────────────────────────────────────────────┐
│                      3. DECISION & ACTION LAYER                        │
│   RiskEngine  +  ConfidenceEngine  ───>  DecisionAgent                 │
│   - AUTO_APPROVE (Safe to merge)                                       │
│   - AUTO_REJECT  (Critical flaw detected — blocks merge)               │
│   - HUMAN_REVIEW_REQUIRED (Disagreement or low evidence)               │
│                                                                        │
│   Actuators:                                                           │
│   • GitHub PR Review Comment (with Automated Repair Diff)              │
│   • GitHub Actions Status Check (Pass / Fail)                          │
│   • Local Interactive Web Dashboard (Flask + React CDN)                │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 3. The Specialized Agents: Roles & Technologies

RAMAV utilizes 7 specialized agents. Each has a specific mandate, strict boundary of authority, and dedicated underlying technology:

| Agent Name | Core Technology | Primary Responsibility | Example Action |
|:---|:---|:---|:---|
| **`SecurityAgent`** | **Semgrep CLI** (AST) + Regex Heuristics fallback | Detects vulnerabilities (SQL injection, hardcoded secrets, unsafe eval/exec). | Flags unparameterized SQL queries in `app/routes/user.py`. |
| **`TestingAgent`** | **Pytest** / stdlib `unittest` via subprocess | Discovers and executes repository tests; checks test coverage of modified endpoints. | Answers Security Agent: *"No adversarial test covers malicious injection input."* |
| **`QualityAgent`** | Python **`ast`** module (Abstract Syntax Tree) | Evaluates complexity, nesting depth, error-handling conventions (`try/except`). | Challenges Security Agent on whether other repository modules use parameterized queries. |
| **`DependencyAgent`** | Manifest Parsers (`requirements.txt`, `package.json`) | Detects unpinned dependencies, supply-chain vulnerabilities, and licensing issues. | Flags deprecated or dangerous packages added to manifests. |
| **`PerformanceAgent`** | Python **`ast`** static inspection | Identifies algorithmic bottlenecks, nested loops (`O(n²)`), and DB queries inside loops. | Detects repeated database queries inside an unindexed loop. |
| **`RepairAgent`** | Rule-based regex/AST code synthesis | Proposes mechanical, deterministic patches to fix detected vulnerabilities. | Generates a unified `diff` replacing `f"SELECT ..."` with `cursor.execute(..., (? ,))`. |
| **`DecisionAgent`** | Deterministic Threshold Policy Engine | Aggregates risk and confidence scores; enforces policy gates without LLM randomness. | Enforces **Critical Override**: Immediately issues `AUTO_REJECT` on any High/Critical flaw. |

### The `Orchestrator`
The Orchestrator is the conductor of the multi-agent system. Rather than simply averaging scores:
- Maintains shared `OrchestratorState`.
- Implements an **`InvestigationPlanner`** (a best-first search algorithm based on `priority = severity * uncertainty * impact / cost`).
- Detects **Disagreements** between agents (e.g., Security says High Risk, but Quality says Low Risk) and attempts to resolve them through targeted evidence requests.

---

## 4. Multi-Agent Communication Protocol

Agents communicate asynchronously over an in-memory **`MessageBus`** using standardized structured message types:

1. **`TASK`**: The Orchestrator assigns a changeset to an agent for analysis.
2. **`REQUEST_EVIDENCE`**: An agent asks another agent for specific empirical proof.
   - *Example:* Security Agent asks Testing Agent: *"Do tests cover malicious string payloads on `/users/<id>`?"*
3. **`RESPONSE`**: The receiving agent provides real evidence from its tool execution.
   - *Example:* Testing Agent runs pytest and replies: *"No tests exist for malicious input."*
4. **`CHALLENGE`**: An agent challenges another agent's assumptions.
   - *Example:* Quality Agent asks Security Agent: *"Does this repository consistently use parameterized queries elsewhere, or is this an isolated exception?"*
5. **`REASSESS`**: An agent adjusts its internal risk and confidence scores based on received evidence.
   - *Example:* Security Agent elevates risk from `0.55 (MEDIUM)` to `0.94 (HIGH)` because the vulnerable route lacks tests.
6. **`DISAGREEMENT`**: Published when two agents evaluate the same file with a large risk gap ($\Delta > 0.35$).
7. **`DECISION`**: Published by the Decision Agent declaring the final merge verdict.

---

## 5. End-to-End Pull Request Flow (What Happens on GitHub)

When a developer opens or updates a Pull Request on GitHub, the following exact lifecycle occurs:

```
[Developer Push] ──> [GitHub Actions Runner] ──> [RAMAV Multi-Agent Engine] ──> [PR Comment & Merge Gate]
```

### Step 1: Trigger & Ingestion
1. The developer pushes a branch and opens a Pull Request on GitHub.
2. GitHub Actions detects the `pull_request` event and triggers `.github/workflows/ramav.yml`.
3. An Ubuntu virtual machine boots up, checks out the PR code, checks out the `NethraK15/RAMAV` engine, and installs dependencies (`flask`, `pytest`, `semgrep`, `requests`).

### Step 2: Change Analysis
`scripts/github_pr_bot.py` starts and calls the **Change Analyzer**:
- Runs `git diff origin/main...HEAD` to isolate only the files modified in this PR.
- Detects programming languages (`.py`, `.js`, etc.).
- Inspects code hints to determine if the changeset touches **database queries**, **API endpoints**, or **dependencies**.

### Step 3: Multi-Agent Analysis & Coordination
The **Orchestrator** initializes:
1. **Initial Dispatch:** All 5 specialized agents analyze the changeset.
   - `SecurityAgent` runs `semgrep scan --config auto --json` against the repo.
   - `TestingAgent` searches for tests and executes `pytest`.
   - `QualityAgent` parses the code's Abstract Syntax Tree.
2. **Coordination Rounds:**
   - Security Agent publishes finding: `Detected possible SQL query formatting`.
   - Security Agent sends `REQUEST_EVIDENCE` to Testing Agent.
   - Testing Agent confirms absence of security regression tests.
   - Security Agent sends `REASSESS` increasing risk to High.
   - Quality Agent challenges conventions.

### Step 4: Risk, Confidence & Decision Policy
1. **Risk Engine** calculates the aggregate risk using weighted category maximums:
   $$\text{Category Risk} = \max(\text{findings in category})$$
   $$\text{Aggregate Risk} = \sum (\text{weight}_i \times \text{Risk}_i)$$
2. **Confidence Engine** calculates evidence completeness and tool reliability (`REAL_TOOL` vs `HEURISTIC`).
3. **Decision Agent** applies the deterministic policy:
   - **Critical Override Rule:** If any finding is `HIGH` or `CRITICAL` (such as an SQL injection), autonomous approval is strictly forbidden $\rightarrow$ **`AUTO_REJECT`**.
   - If risk is low ($\le 0.25$) and confidence is high ($\ge 0.70$) $\rightarrow$ **`AUTO_APPROVE`**.
   - If agents disagree or evidence is incomplete $\rightarrow$ **`HUMAN_REVIEW_REQUIRED`**.

### Step 5: Automated Repair Suggestion
If vulnerabilities exist, the **Repair Agent** inspects the offending files and computes an automated patch (e.g. rewriting f-string SQL queries into parameterized queries with tuples). It computes a unified `diff`.

### Step 6: PR Feedback & Gate Enforcement
1. **Posts Review Comment:** Uses the GitHub REST API (`POST /repos/{owner}/{repo}/issues/{pr}/comments`) to post a formatted review containing:
   - Decision badge (🔴 `AUTO_REJECT` / 🟢 `AUTO_APPROVE`)
   - Metrics summary table (Risk, Confidence, Files changed)
   - Evidence table with file paths and line numbers
   - Unified `diff` repair code suggestion
   - Collapsible agent conversation trace
2. **Enforces Merge Gate:** If `AUTO_REJECT`, the script exits with code `1`, failing the GitHub Action check and **blocking the PR from being merged**.

---

## 6. Closed-Loop Verification (The Repair Guarantee)

In traditional systems, when an AI generates a code fix, it is assumed to work. 

**RAMAV enforces a strict Closed-Loop Verification rule:**
> *"A repair is NEVER trusted just because a patch was generated."*

When a repair is proposed:
1. The Repair Agent applies the patch to an isolated, scratch copy of the repository.
2. The **entire multi-agent pipeline** runs again from scratch against the patched tree:
   - Semgrep re-scans to verify the vulnerability is 100% gone.
   - Pytest re-runs to ensure the patch did not break existing functionality.
3. Only if the vulnerability finding is completely absent AND all unit tests pass does RAMAV report **`Repair verified`**.

---

## 7. PEAS Framework Specification

For formal AI evaluation and academic defense, RAMAV is classified under the **PEAS** model:

- **Performance Measure ($P$):**
  - Zero unsafe autonomous approvals (safety-critical priority).
  - High decision confidence ($> 70\%$).
  - Fast execution time ($< 60\text{s}$).
  - High evidence completeness and explainability.
- **Environment ($E$):**
  - Git repositories (commits, branches, PRs).
  - Programming source files (Python, JavaScript).
  - Test suites and dependency manifest files.
- **Actuators ($A$):**
  - GitHub PR review comment publisher.
  - GitHub Actions check run status (Pass / Fail exit codes).
  - Automated repair patch synthesizer.
  - Local SQLite database persistence (`ramav.db`).
- **Sensors ($S$):**
  - Git diff inspection (`git diff origin/main...HEAD`).
  - Semgrep AST scanner output.
  - Pytest / Unittest test runner execution results.
  - Python `ast` syntax tree parser.

---

## 8. Common Viva & Interview Questions & Model Answers

### Q1: Why not just use SonarQube, GitHub Code Scanning, or standard Semgrep?
> **Answer:** Standalone static analysis tools operate in silos—they only detect patterns, but cannot reason about context. Semgrep will tell you a line has string formatting, but it doesn't know if that endpoint is covered by tests, whether it violates repo-wide conventions, or if other agents disagree. RAMAV is a **coordination and decision layer**: it orchestrates communication between security, testing, and quality agents to negotiate risk before rendering a deterministic decision.

### Q2: Why don't you use an LLM for the final decision?
> **Answer:** LLMs are non-deterministic and prone to hallucination. A security merge gate must be reproducible, auditable, and mathematically sound. RAMAV uses a deterministic policy with explicit mathematical weights and thresholds. LLMs can assist in optional explanatory text, but the decision policy never depends on an LLM.

### Q3: What is the "Critical Override" rule?
> **Answer:** In traditional naive systems, averaging scores across multiple checks allows a high-risk security flaw to be watered down by clean scores from documentation, formatting, and performance checks. RAMAV's Critical Override rule guarantees that any `HIGH` or `CRITICAL` finding immediately overrides the aggregate score and forces an `AUTO_REJECT`.

### Q4: What happens if a tool like Semgrep or Pytest is missing from the environment?
> **Answer:** RAMAV is designed with truthful provenance. If Semgrep is missing, the Security Agent falls back to a deterministic heuristic scanner, but labels the finding as `HEURISTIC` instead of `REAL_TOOL`. The Confidence Engine reduces the confidence score accordingly, and because confidence drops, the system escalates to `HUMAN_REVIEW_REQUIRED` instead of falsely auto-approving.
