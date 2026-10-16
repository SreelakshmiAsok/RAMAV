"""
Repair Agent (optional)
========================
Proposes a fix for a detected vulnerability (currently: rewrites naive
f-string / %-formatted SQL calls into parameterized queries). Critically,
this agent's output is NEVER trusted on its own -- after it patches the
file, the Security/Testing/Quality agents are re-run against the patched
copy, and only if the vulnerability finding is actually gone does the
pipeline report "Repair verified." Otherwise: HUMAN REVIEW REQUIRED.
"""
from __future__ import annotations

import re
import shutil


class RepairAgent:
    name = "repair_agent"

    def propose_patch(self, file_path: str) -> tuple[bool, str]:
        """Attempts a mechanical, rule-based rewrite of unsafe SQL string
        construction into parameterized form. Returns (changed, description).
        This is intentionally NOT an LLM free-write -- a narrow, explainable
        transformation that we can then re-verify."""
        with open(file_path, "r") as fh:
            src = fh.read()

        changed = False
        description_parts = []

        # Pattern: cursor.execute(f"... '{var}' ...") or f"... {var} ..." ->
        #          cursor.execute("... ? ...", (var,))
        # We strip a single pair of quotes immediately around a placeholder
        # (SELECT ... WHERE col = '{var}') since the parameterized form
        # must NOT keep the quotes -- `'?'` would bind a literal string "?"
        # rather than substituting a real parameter, which is a silent bug.
        fstring_pattern = re.compile(
            r'(cursor\.execute)\(\s*f"((?:[^"{}]|\{[^{}]*\})*)"\s*\)'
        )

        def _rewrite(match):
            nonlocal changed
            call, body = match.group(1), match.group(2)
            placeholders = re.findall(r"\{([^{}]*)\}", body)
            if not placeholders:
                return match.group(0)
            # remove a quote immediately before/after the { } if present
            new_body = re.sub(r"'\{[^{}]*\}'", "?", body)
            new_body = re.sub(r"\{[^{}]*\}", "?", new_body)
            params = ", ".join(placeholders)
            changed = True
            description_parts.append(f"Rewrote f-string SQL call to parameterized query using ({params},)")
            return f'{call}("{new_body}", ({params},))'

        new_src = fstring_pattern.sub(_rewrite, src)

        if changed:
            backup = file_path + ".bak"
            shutil.copyfile(file_path, backup)
            with open(file_path, "w") as fh:
                fh.write(new_src)

        return changed, "; ".join(description_parts) if description_parts else "No mechanical rewrite pattern matched."
