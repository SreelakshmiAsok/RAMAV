"""
Change Analyzer
===============
Inspects a directory (a "PR" in local-demo mode is just a folder of changed
files plus metadata) and builds a structured ChangeSet describing what
changed. This becomes the initial state handed to the Orchestrator.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

from app.integrations.git_utils import diff_against_parent, is_git_repo

SECURITY_SENSITIVE_HINTS = ["sql", "query", "execute", "cursor", "password", "auth", "token", "eval(", "exec("]
DB_HINTS = ["select ", "insert ", "update ", "delete ", "cursor.execute", "session.query", ".execute("]
ENDPOINT_HINTS = ["@app.route", "@router.", "def get(", "def post(", "APIRouter", "@app.get", "@app.post"]


@dataclass
class ChangeSet:
    pr_id: str
    files_changed: int = 0
    lines_added: int = 0
    lines_deleted: int = 0
    languages: list[str] = field(default_factory=list)
    changed_files: list[str] = field(default_factory=list)
    security_sensitive: bool = False
    database_access: bool = False
    tests_changed: bool = False
    dependency_files_changed: list[str] = field(default_factory=list)
    api_endpoints_touched: bool = False

    def to_dict(self):
        return self.__dict__.copy()


LANG_BY_EXT = {".py": "python", ".js": "javascript", ".ts": "typescript", ".tsx": "typescript", ".jsx": "javascript"}


class ChangeAnalyzer:
    def analyze_directory(self, path: str, pr_id: str, changed_files: list[str] = None) -> ChangeSet:
        cs = ChangeSet(pr_id=pr_id)
        if changed_files is not None:
            files = changed_files
        elif is_git_repo(path):
            files = diff_against_parent(path)
        else:
            files = self._walk(path)
        cs.changed_files = files
        cs.files_changed = len(files)

        langs = set()
        for rel in files:
            full = os.path.join(path, rel)
            _, ext = os.path.splitext(rel)
            if ext in LANG_BY_EXT:
                langs.add(LANG_BY_EXT[ext])

            if "test" in rel.lower():
                cs.tests_changed = True

            if os.path.basename(rel) in ("requirements.txt", "package.json", "package-lock.json", "pyproject.toml"):
                cs.dependency_files_changed.append(rel)

            if not os.path.isfile(full):
                continue
            try:
                with open(full, "r", errors="ignore") as fh:
                    content = fh.read()
            except OSError:
                continue

            lower = content.lower()
            cs.lines_added += len(content.splitlines())

            if any(h in lower for h in SECURITY_SENSITIVE_HINTS):
                cs.security_sensitive = True
            if any(h in lower for h in DB_HINTS):
                cs.database_access = True
            if any(h in content for h in ENDPOINT_HINTS):
                cs.api_endpoints_touched = True

        cs.languages = sorted(langs)
        return cs

    def _walk(self, path: str) -> list[str]:
        out = []
        for root, _dirs, filenames in os.walk(path):
            for fn in filenames:
                full = os.path.join(root, fn)
                rel = os.path.relpath(full, path)
                out.append(rel)
        return out
