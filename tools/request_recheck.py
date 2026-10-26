"""request_recheck: run the security rules again on the changed files (reads only).
Used by: Fixer & Validator, who ASKS; the Auditor's own tool (run_security_rules) does the work.

The rules file is the one registered when the temporary copy was made, so the Fixer cannot
choose a weaker one. ``clear`` is true only when no rule matches remain in the changed files.
If any file could not be checked, or any rule could not run, the answer is NOT "clear": the
call fails with auditor_failed and the fix is not called verified.
"""
from __future__ import annotations

import os

from . import _schema
from ._safety import SafetyError
from ._workspace import require_temp_copy
from .run_security_rules import run_security_rules

TOOL = "request_recheck"
HANDLING = "not_verified"


def request_recheck(workspace: str, files: list[str]) -> dict:
    args = {"workspace": workspace, "files": files}
    _schema.validate_args(TOOL, args)

    if not os.path.isdir(workspace):
        return _schema.fail(TOOL, args, "workspace_not_found", f"workspace {workspace!r} is not a folder", HANDLING)
    try:
        marker = require_temp_copy(workspace)
    except SafetyError as exc:
        return _schema.fail(TOOL, args, "outside_workspace", str(exc), HANDLING)
    rules_file = marker.get("rules_file")
    if not rules_file or not os.path.isfile(rules_file):
        return _schema.fail(TOOL, args, "rules_unavailable",
                            "the rules file registered for this run is missing", HANDLING)

    inner = run_security_rules(workspace, rules_file, files)["response"]
    if not inner["ok"]:
        return _schema.fail(TOOL, args, "auditor_failed", "the rules could not be run: " + inner["error"]["message"], HANDLING)
    result = inner["result"]
    if result["skipped_rules"] or result.get("skipped_files"):
        problems = [f"rule {r['rule_id']}: {r['reason']}" for r in result["skipped_rules"]]
        problems += [f"file {f['file']}: {f['reason']}" for f in result.get("skipped_files", [])]
        return _schema.fail(TOOL, args, "auditor_failed",
                            "the re-check was incomplete, so it cannot be called clear: " + "; ".join(problems), HANDLING)
    matches = result["matches"]
    return _schema.ok(TOOL, args, {"clear": not matches, "files_checked": list(files), "matches": matches})
