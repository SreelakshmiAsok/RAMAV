# Tool / Package Selection — RAMAV

For each technology: what it does, why used, the alternative considered,
install instructions, and its role in the project.

| Technology | What it does | Why chosen | Alternative | Install | Role here |
|---|---|---|---|---|---|
| **Python 3.12** | General-purpose language | Best ecosystem for both AST analysis and web APIs; matches the demo repo's own language | Node.js/TypeScript throughout | Pre-installed on most systems; else python.org | Backend + agent logic |
| **Flask** | Lightweight WSGI web framework | Actually installable in the authoring sandbox (no network access — see `docs/ENVIRONMENT_NOTES.md`); trivial to install anywhere | **FastAPI** (originally specified) — async, auto-OpenAPI docs, Pydantic validation | `pip install flask` | HTTP layer only — all logic lives in `app/agents`, `app/risk`, etc. |
| stdlib `dataclasses` | Structured data classes | No network to install Pydantic in the sandbox; dataclasses cover validation needs here | **Pydantic** (originally specified) | Built into Python | `AgentMessage`, `Finding`, `Evidence`, `ChangeSet` |
| stdlib `sqlite3` | Embedded SQL database | Zero setup; the spec itself names SQLite as an acceptable local-demo fallback | **SQLAlchemy + PostgreSQL** (originally specified) | Built into Python | Persists analysis runs for `/api/history` |
| **React 18 (UMD) + htm** | UI library, loaded via CDN with no build step | `npm install` returned `403 Forbidden` in the sandbox (no registry access); a no-build dashboard also removes an entire class of demo-day risk | **Vite + TypeScript** build (originally specified) | None — loaded via `<script>` tags from unpkg | Dashboard — Agent Conversation, Findings, Decision, PEAS, etc. |
| **Tailwind-style utility CSS** (hand-written, not the Tailwind CDN build) | Small utility classes for spacing/layout | Kept the CSS in one auditable file (`frontend/styles.css`) rather than pulling another CDN dependency | Tailwind Play CDN | N/A | Dashboard styling |
| stdlib `unittest` | Test runner | `pytest` is not installed and could not be installed (no network); `scripts/run_tests.sh` uses pytest automatically if present, else unittest | **pytest** (originally specified) | Built into Python | All 35 backend tests |
| **Semgrep** | Pattern-based static analysis across many languages | Industry-standard, exactly what the spec asks for | ESLint security plugins, Bandit (Python-only) | `pip install semgrep` (not installed in the sandbox — see `docs/SEMGREP_GUIDE.md`) | Security Agent's primary evidence source when available |
| Deterministic fallback analyzer | A handful of regex/AST rules for SQLi/eval/hardcoded secrets | Guarantees the pipeline still produces real evidence when Semgrep is absent, with correct `HEURISTIC` labeling | — | Built-in (`app/integrations/semgrep_adapter.py`) | Security Agent's fallback evidence source |
| **git** | Version control | Already the source of truth for "what changed"; using real `git diff` instead of a hand-listed file set is more defensible | Manual "changed files" list | Pre-installed on almost every dev machine | Change Analyzer's real diff source |
| **Ollama** (optional) | Local LLM server | Keeps LLM use fully local/free and optional | OpenAI API, Anthropic API | `curl https://ollama.ai/install.sh \| sh` then `ollama pull llama3` | Optional explanation text only — never the decision itself |
| **Docker / docker-compose** | Containerization | Convenience for graders who prefer one-command setup | Bare-metal venv (also fully supported and what was actually tested) | docker.com | Optional; files provided, not exercised in the no-Docker sandbox |

## Flask vs FastAPI (why the port is mechanical)

Both are thin routing layers over plain functions returning JSON. The main
differences that matter for a port:
- FastAPI wants `def route(body: SomeModel)` with a Pydantic model;
  `dataclasses.asdict()` output already matches what those models would
  validate, so this is a rename, not a rewrite.
- FastAPI auto-generates OpenAPI docs at `/docs` for free — worth doing on
  a machine with internet access, and easy to add since routes are already
  documented via docstrings.
- Async: none of RAMAV's routes need to be async (everything is CPU-bound
  local analysis, not I/O-bound network calls), so `async def` buys nothing
  functionally here.

## SQLite vs PostgreSQL

The spec explicitly allows SQLite as a local-demo fallback. Since this
build's target is "runnable locally by a student on a normal laptop," and
since a classroom demo does not need concurrent writers, SQLite is not just
a workaround here — it is the more appropriate choice for the stated use
case. `app/database/db.py` isolates all SQL behind small functions, so
swapping to SQLAlchemy+Postgres later touches one file.
