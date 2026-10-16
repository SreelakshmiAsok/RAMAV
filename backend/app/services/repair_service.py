"""
Repair + Revalidation Service
=============================
Implements the closed-loop requirement: a repair is NEVER trusted just
because an automated patch was generated. After the Repair Agent patches a
file, the ENTIRE multi-agent pipeline is re-run from scratch against the
patched working tree, and only if the originating vulnerability finding is
actually gone does the service report "Repair verified."
"""
from __future__ import annotations

import glob
import os
import shutil
import tempfile

from app.agents.orchestrator import Orchestrator
from app.agents.repair_agent import RepairAgent
from app.evidence.store import Severity


def run_repair_and_revalidate(repo_path: str, pr_id: str) -> dict:
    # 1. Run the normal pipeline first, exactly like any other PR.
    pre_orch = Orchestrator(repo_path, pr_id)
    pre_result = pre_orch.run()

    critical_findings = [
        f for f in pre_orch.store.all_findings()
        if f.category == "security" and f.severity in (Severity.HIGH, Severity.CRITICAL)
    ]

    if not critical_findings:
        return {
            "pre_repair": pre_result,
            "repair_attempted": False,
            "repair_verified": False,
            "post_repair": None,
            "note": "No security finding required repair.",
        }

    # 2. Work on a throwaway copy so the canonical demo repo on disk is
    #    never mutated by a repair attempt (repeatable demos).
    scratch = tempfile.mkdtemp(prefix="ramav_repair_")
    work_dir = os.path.join(scratch, "repo")
    shutil.copytree(repo_path, work_dir)

    repair_agent = RepairAgent()
    patch_log = []
    any_patch_applied = False
    for finding in critical_findings:
        if not finding.file:
            continue
        full_path = os.path.join(work_dir, finding.file)
        if not os.path.isfile(full_path):
            continue
        changed, description = repair_agent.propose_patch(full_path)
        patch_log.append({"file": finding.file, "changed": changed, "description": description})
        any_patch_applied = any_patch_applied or changed

    if any_patch_applied:
        # Commit the patch as a new git commit so the Change Analyzer's
        # `git diff HEAD~1..HEAD` still works against the patched tree.
        import subprocess
        subprocess.run(["git", "add", "-A"], cwd=work_dir, capture_output=True)
        subprocess.run(["git", "-c", "user.email=repair@ramav.local", "-c", "user.name=RAMAV Repair Agent",
                         "commit", "-q", "-m", "fix: apply automated parameterized-query repair"],
                        cwd=work_dir, capture_output=True)

    # 3. Re-run the FULL pipeline (Security + Testing + Quality, real
    #    pytest/unittest execution, real re-scan) against the patched tree.
    post_orch = Orchestrator(work_dir, pr_id + "-repaired")
    post_result = post_orch.run()

    post_critical = [
        f for f in post_orch.store.all_findings()
        if f.category == "security" and f.severity in (Severity.HIGH, Severity.CRITICAL)
    ]
    tests_still_pass = not any(
        f.category == "testing" and "failing" in f.title.lower()
        for f in post_orch.store.all_findings()
    )

    repair_verified = any_patch_applied and not post_critical and tests_still_pass

    shutil.rmtree(scratch, ignore_errors=True)

    return {
        "pre_repair": pre_result,
        "repair_attempted": any_patch_applied,
        "patch_log": patch_log,
        "post_repair": post_result,
        "repair_verified": repair_verified,
        "note": (
            "Repair verified: the originating vulnerability finding is gone and tests still pass."
            if repair_verified else
            "HUMAN REVIEW REQUIRED: repair could not be automatically verified as resolving the "
            "vulnerability. Do not treat patch generation alone as a fix."
        ),
    }
