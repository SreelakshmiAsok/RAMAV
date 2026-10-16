"""
Git integration for local-demo mode.

Each demo scenario is a real git repository with a "baseline" commit and a
"PR" commit on top of it (see scripts/setup_demo_repos.py). We use an actual
`git diff --name-only <parent>..HEAD` to discover the changed files, rather
than hand-listing them -- this is what "Change Analyzer inputs: git
repository, commit range" means in practice for the local demo.
"""
from __future__ import annotations

import subprocess


def is_git_repo(path: str) -> bool:
    try:
        subprocess.run(["git", "rev-parse", "--is-inside-work-tree"], cwd=path,
                        capture_output=True, text=True, check=True)
        return True
    except Exception:
        return False


def diff_against_parent(path: str) -> list[str]:
    """Returns the list of files changed in HEAD relative to origin/main or HEAD~1.
    Falls back to listing every tracked file if there is only one commit."""
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "origin/main...HEAD"],
            cwd=path, capture_output=True, text=True, check=True,
        )
        files = [f for f in proc.stdout.splitlines() if f.strip()]
        if files:
            return files
    except Exception:
        pass
    try:
        proc = subprocess.run(
            ["git", "diff", "--name-only", "HEAD~1..HEAD"],
            cwd=path, capture_output=True, text=True, check=True,
        )
        files = [f for f in proc.stdout.splitlines() if f.strip()]
        if files:
            return files
    except Exception:
        pass
    try:
        proc = subprocess.run(["git", "ls-files"], cwd=path, capture_output=True, text=True, check=True)
        return [f for f in proc.stdout.splitlines() if f.strip()]
    except Exception:
        return []


def commit_range_summary(path: str) -> dict:
    try:
        proc = subprocess.run(
            ["git", "log", "-2", "--pretty=format:%H|%s|%an|%ad", "--date=iso"],
            cwd=path, capture_output=True, text=True, check=True,
        )
        commits = []
        for line in proc.stdout.splitlines():
            parts = line.split("|", 3)
            if len(parts) == 4:
                commits.append({"hash": parts[0][:10], "message": parts[1], "author": parts[2], "date": parts[3]})
        return {"commits": commits}
    except Exception:
        return {"commits": []}
