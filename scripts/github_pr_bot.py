#!/usr/bin/env python3
"""
RAMAV GitHub PR Bot
===================
Runs RAMAV against a Pull Request in GitHub Actions, analyzes the changeset
using specialized agents, and posts an interactive review comment with
risk assessment, findings, and automated repair suggestions.

Can be run locally in dry-run mode:
    python3 scripts/github_pr_bot.py --dry-run --repo-path .
"""
from __future__ import annotations

import argparse
import difflib
import json
import os
import re
import sys

# Ensure backend modules can be imported
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(REPO_ROOT, "backend"))

from app.agents.orchestrator import Orchestrator


BOT_SIGNATURE = "<!-- ramav-pr-bot-comment -->"


def generate_repair_diff(file_path: str) -> str | None:
    """Computes a unified diff proposing parameterized query replacement if vulnerable."""
    if not os.path.isfile(file_path):
        return None
    try:
        with open(file_path, "r", errors="ignore") as fh:
            original = fh.read()
    except OSError:
        return None

    fstring_pattern = re.compile(r'(cursor\.execute)\(\s*f"((?:[^"{}]|\{[^{}]*\})*)"\s*\)')
    changed = False

    def _rewrite(match):
        nonlocal changed
        call, body = match.group(1), match.group(2)
        placeholders = re.findall(r"\{([^{}]*)\}", body)
        if not placeholders:
            return match.group(0)
        new_body = re.sub(r"'\{[^{}]*\}'", "?", body)
        new_body = re.sub(r"\{[^{}]*\}", "?", new_body)
        params = ", ".join(placeholders)
        changed = True
        return f'{call}("{new_body}", ({params},))'

    patched = fstring_pattern.sub(_rewrite, original)
    if changed:
        diff_lines = list(difflib.unified_diff(
            original.splitlines(keepends=True),
            patched.splitlines(keepends=True),
            fromfile=f"a/{os.path.basename(file_path)}",
            tofile=f"b/{os.path.basename(file_path)}",
        ))
        return "".join(diff_lines)
    return None


def format_pr_comment(result: dict, pr_number: str, repo_path: str = "") -> tuple[str, str]:
    """Generates a GitHub-flavored markdown review comment from RAMAV analysis results."""
    decision = result.get("decision", {})
    outcome = decision.get("outcome", "HUMAN_REVIEW_REQUIRED")
    risk = decision.get("risk", 0.0)
    confidence = decision.get("confidence", 0.0)
    reasons = decision.get("reasons", [])
    changeset = result.get("changeset", {})
    findings = result.get("findings", [])
    messages = result.get("messages", [])

    base_dir = repo_path or REPO_ROOT

    if outcome == "AUTO_APPROVE":
        badge = "🟢 **AUTO-APPROVE**"
        header_desc = "All specialized agents converged on low risk with sufficient confidence. PR is safe to merge."
    elif outcome == "AUTO_REJECT":
        badge = "🔴 **AUTO-REJECT**"
        header_desc = "High-risk issues or critical vulnerabilities detected. Autonomous merge blocked."
    else:
        badge = "🟡 **HUMAN REVIEW REQUIRED**"
        header_desc = "Agent disagreement, incomplete evidence, or moderate risk detected. Manual inspection needed."

    comment = [
        BOT_SIGNATURE,
        f"## 🛡️ RAMAV Automated PR Validation: {badge}",
        f"> {header_desc}",
        "",
        "### 📊 Validation Summary",
        "| Metric | Value | Detail |",
        "| :--- | :--- | :--- |",
        f"| **Decision** | `{outcome}` | Policy outcome |",
        f"| **Aggregated Risk** | `{risk:.2f}` / `1.00` | Weighted multi-agent risk score |",
        f"| **Evidence Confidence** | `{confidence:.0%}` | Provenance & completeness confidence |",
        f"| **Files Changed** | `{changeset.get('files_changed', 0)}` file(s) | `{', '.join(changeset.get('changed_files', [])[:5]) or 'none'}` |",
        f"| **Security Sensitive** | `{'Yes' if changeset.get('security_sensitive') else 'No'}` | Database / auth / query touchpoints |",
        "",
    ]

    if reasons:
        comment.append("### 📋 Decision Rationale")
        for r in reasons:
            comment.append(f"- {r}")
        comment.append("")

    # Findings section
    if findings:
        comment.append("### 🔍 Findings & Evidence")
        comment.append("| Category | Severity | Title | File : Line | Source |")
        comment.append("| :--- | :--- | :--- | :--- | :--- |")
        for f in findings:
            cat = f.get("category", "").capitalize()
            sev = f.get("severity", "LOW")
            sev_icon = "🔴" if sev in ("CRITICAL", "HIGH") else ("🟡" if sev == "MEDIUM" else "🔵")
            title = f.get("title", "")
            file_loc = f"`{f.get('file')}:{f.get('line')}`" if f.get("file") else "—"
            source = f"`{f.get('source_type', 'HEURISTIC')}`"
            comment.append(f"| **{cat}** | {sev_icon} `{sev}` | {title} | {file_loc} | {source} |")
        comment.append("")

    # Automated Suggestions / Repairs
    repair_suggestions = []
    seen_files = set()
    for f in findings:
        file_path = f.get("file")
        if file_path and file_path not in seen_files:
            seen_files.add(file_path)
            full_path = os.path.join(base_dir, file_path)
            diff = generate_repair_diff(full_path)
            if diff:
                repair_suggestions.append((file_path, diff))

    if repair_suggestions:
        comment.append("### 💡 Automated Repair Suggestions")
        comment.append("RAMAV identified safe parameterized query repairs for the following file(s):")
        for rel_file, diff in repair_suggestions:
            comment.append(f"#### `{rel_file}`")
            comment.append("```diff")
            comment.append(diff.strip())
            comment.append("```")
        comment.append("")

    # Agent conversation trace (collapsible)
    if messages:
        comment.append("<details>")
        comment.append(f"<summary><b>🤖 Agent-to-Agent Coordination Trace ({len(messages)} messages)</b></summary>")
        comment.append("")
        comment.append("| Step | Type | Sender → Receiver | Content |")
        comment.append("| :--- | :--- | :--- | :--- |")
        for i, m in enumerate(messages, start=1):
            sender = m.get("sender", "")
            receiver = m.get("receiver", "")
            mtype = m.get("type", "")
            parties = f"`{sender}` → `{receiver}`" if receiver else f"`{sender}`"
            content = (m.get("content") or m.get("question") or "").replace("\n", " ")
            comment.append(f"| {i} | `{mtype}` | {parties} | {content[:90]}... |")
        comment.append("</details>")
        comment.append("")

    comment.append("---")
    comment.append("*Report generated autonomously by [RAMAV](https://github.com/NethraK15) multi-agent validation layer.*")

    return "\n".join(comment), outcome


def post_to_github(comment_body: str, repo: str, pr_number: str, token: str) -> bool:
    """Posts or updates comment on GitHub PR using GitHub REST API."""
    import requests

    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    # Check for existing comment to update (avoid duplicates)
    comments_url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
    try:
        res = requests.get(comments_url, headers=headers, timeout=15)
        if res.status_code == 200:
            for item in res.json():
                if BOT_SIGNATURE in item.get("body", ""):
                    comment_id = item["id"]
                    update_url = f"https://api.github.com/repos/{repo}/issues/comments/{comment_id}"
                    put_res = requests.patch(update_url, headers=headers, json={"body": comment_body}, timeout=15)
                    if put_res.status_code in (200, 201):
                        print(f"Updated existing RAMAV comment #{comment_id} on PR #{pr_number}")
                        return True
    except Exception as exc:
        print(f"Notice: Failed to query existing comments ({exc}). Proceeding to create fresh comment.")

    # Post new comment
    post_res = requests.post(comments_url, headers=headers, json={"body": comment_body}, timeout=15)
    if post_res.status_code in (200, 201):
        print(f"Successfully posted RAMAV validation comment to PR #{pr_number}")
        return True
    else:
        print(f"Failed to post comment to GitHub: {post_res.status_code} {post_res.text}")
        if post_res.status_code == 403:
            print("\n💡 HINT: To enable posting PR comments automatically, go to:")
            print("   Settings -> Actions -> General -> Workflow permissions -> Select 'Read and write permissions'\n")
        return False


def main():
    parser = argparse.ArgumentParser(description="RAMAV GitHub PR Bot")
    parser.add_argument("--repo-path", default=os.getcwd(), help="Path to local git clone")
    parser.add_argument("--pr-number", default=os.environ.get("PR_NUMBER"), help="Pull request number")
    parser.add_argument("--github-repo", default=os.environ.get("GITHUB_REPOSITORY"), help="GitHub owner/repo")
    parser.add_argument("--github-token", default=os.environ.get("GITHUB_TOKEN"), help="GitHub Actions token")
    parser.add_argument("--dry-run", action="store_true", help="Print comment to stdout instead of posting to GitHub")
    parser.add_argument("--fail-on-reject", action="store_true", default=True, help="Exit with code 1 if AUTO_REJECT")
    args = parser.parse_args()

    repo_path = os.path.abspath(args.repo_path)
    pr_number = args.pr_number or "1"

    print(f"== RAMAV PR Bot: Analyzing repository '{repo_path}' for PR #{pr_number} ==")
    orch = Orchestrator(repo_path, f"PR-{pr_number}")
    result = orch.run()

    comment_markdown, outcome = format_pr_comment(result, pr_number, repo_path)

    # Always write to GitHub Action Job Summary if running in CI
    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        try:
            with open(step_summary, "a") as fh:
                fh.write("\n" + comment_markdown + "\n")
        except Exception:
            pass

    # Always output formatted report to the action logs
    print("\n" + "=" * 30 + " RAMAV PR VALIDATION REPORT " + "=" * 30)
    print(comment_markdown)
    print("=" * 86 + "\n")

    if not args.dry_run and args.github_token:
        if args.github_repo:
            post_to_github(comment_markdown, args.github_repo, pr_number, args.github_token)

    if args.fail_on_reject and outcome == "AUTO_REJECT":
        print(f"\n[RAMAV Check Result: FAILED] Outcome was {outcome}. Blocking PR merge.")
        sys.exit(1)
    else:
        print(f"\n[RAMAV Check Result: SUCCESS] Outcome was {outcome}.")
        sys.exit(0)


if __name__ == "__main__":
    main()
