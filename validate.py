#!/usr/bin/env python3
"""Validate payloads against schemas/ and run the checks JSON Schema cannot express.

Run:  python3 validate.py

Two layers, in this order:
  1. schema: the JSON Schema in schemas/.
  2. code:   checks a schema cannot state. They run only on payloads that passed layer 1.
     - quoted_code really appears at that file and line (secrets, emails, phones may be
       <SECRET_n>, <EMAIL_n>, <PHONE_n> placeholders)
     - confidence is a finite number between 0 and 1 (a schema lets NaN through)
     - patch_diff touches only files inside the temporary copy, deletes nothing, and the
       temporary copy is not the original folder
     - totals match the findings; rule ids are unique; each field is written by its owner

Each built-in payload says which layer must reject it. Exit code 0 means every payload behaved
as expected. Uses fake data and golden/ read-only; temporary copies live in a temp folder.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parent
SCHEMA_DIR = ROOT / "schemas"
GOLDEN = ROOT / "golden"
OWNERS = {"orchestrator", "auditor", "investigator", "fixer_validator"}
TOOLS = ["list_files", "read_file", "run_security_rules", "read_code_structure",
         "apply_patch", "run_tests", "request_recheck"]
PLACEHOLDER = re.compile(r"<(?:SECRET|EMAIL|PHONE)_\d+>")


# --------------------------------------------------------------------------- schemas
def load_schemas():
    schemas = {}
    for path in sorted(SCHEMA_DIR.glob("*.schema.json")):
        schemas[path.name.removesuffix(".schema.json")] = json.loads(path.read_text(encoding="utf-8"))
    registry = Registry().with_resources([(s["$id"], Resource.from_contents(s)) for s in schemas.values()])
    return schemas, registry


SCHEMAS, REGISTRY = load_schemas()


def _short(text: str, limit: int = 150) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 3] + "..."


def schema_errors(name: str, payload) -> list[str]:
    validator = Draft202012Validator(SCHEMAS[name], registry=REGISTRY)
    errors = sorted(validator.iter_errors(payload), key=lambda e: [str(p) for p in e.absolute_path])
    return [f"{'/'.join(str(p) for p in e.absolute_path) or '(root)'}: {_short(e.message)}" for e in errors]


# --------------------------------------------------------------------------- code checks
def _inside(base: Path, rel: str) -> bool:
    """True when rel, resolved against base, stays inside base."""
    if re.match(r"^(?:[A-Za-z]:|[/\\])", rel):
        return False
    base = Path(base).resolve()
    target = (base / rel).resolve()
    return target == base or base in target.parents


def check_confidence(where: str, value) -> list[str]:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return [f"{where}: confidence must be a number"]
    if not math.isfinite(value) or not 0 <= value <= 1:
        return [f"{where}: confidence {value!r} is not between 0 and 1"]
    return []


def check_quoted_code(where: str, finding: dict, project_root: Path) -> list[str]:
    evidence = finding["evidence"]
    file, line, quoted = evidence["file"], evidence["line"], evidence["quoted_code"]
    if (finding["file"], finding["line"]) != (file, line):
        return [f"{where}: evidence points at {file}:{line} but the finding at {finding['file']}:{finding['line']}"]
    if not _inside(project_root, file):
        return [f"{where}: evidence file {file!r} is outside the project folder"]
    path = Path(project_root) / file
    if not path.is_file():
        return [f"{where}: evidence file {file!r} does not exist"]
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    if not 1 <= line <= len(lines):
        return [f"{where}: {file} has {len(lines)} lines, there is no line {line}"]
    # Never echo the real line: it may hold the secret the placeholder hides.
    pattern = ".+?".join(re.escape(part) for part in PLACEHOLDER.split(quoted.strip()))
    if re.fullmatch(pattern, lines[line - 1].strip()) is None:
        return [f"{where}: quoted_code does not appear at {file} line {line}"]
    return []


def _diff_targets(diff: str) -> list[tuple[str, str]]:
    targets = []
    for line in diff.splitlines():
        if line.startswith(("--- ", "+++ ")):
            targets.append((line[:3], line[4:].split("\t")[0].strip()))
        elif line.startswith(("rename from ", "rename to ", "copy from ", "copy to ")):
            verb, direction, name = line.split(" ", 2)
            targets.append((f"{verb} {direction}", name.strip()))
    return targets


def check_patch_diff(where: str, diff, workspace, original_root=None) -> list[str]:
    if diff is None:
        return []
    ws = Path(workspace)
    if not ws.is_dir():
        return [f"{where}: workspace {str(workspace)!r} is not a folder"]
    if original_root is not None and ws.resolve() == Path(original_root).resolve():
        return [f"{where}: workspace is the original folder; patches go to the temporary copy only"]
    targets = _diff_targets(diff)
    if not targets:
        return [f"{where}: patch_diff has no file headers, so its files cannot be checked"]
    problems = []
    for kind, raw in targets:
        if raw == "/dev/null":
            if kind == "+++":
                problems.append(f"{where}: patch_diff deletes a file (never allowed)")
            continue
        rel = raw[2:] if kind in ("---", "+++") and raw[:2] in ("a/", "b/") else raw
        if not _inside(ws, rel):
            problems.append(f"{where}: '{kind} {raw}' is outside the temporary copy")
    return problems


def check_totals(output: dict) -> list[str]:
    findings, totals = output["findings"], output["totals"]

    def count(status):
        return sum(1 for f in findings if f["status"] == status)

    expected = {"found": len(findings), "fixed_and_verified": count("verified_awaiting_approval"),
                "rejected": count("rejected"), "needs_a_person": count("needs_a_person"),
                "remaining": count("not_processed")}
    return [f"totals/{k}: is {totals[k]}, the findings give {v}" for k, v in expected.items() if totals[k] != v]


def check_output(output: dict, ctx: dict) -> list[str]:
    problems = []
    for i, f in enumerate(output["findings"]):
        where = f"findings/{i}"
        problems += check_confidence(f"{where}/confidence", f["confidence"])
        problems += check_quoted_code(f"{where}/evidence/quoted_code", f, ctx["project_root"])
        problems += check_patch_diff(f"{where}/patch_diff", f["patch_diff"], ctx["workspace"], ctx["project_root"])
    return problems + check_totals(output)


def check_rules(rules: dict) -> list[str]:
    seen, problems = set(), []
    for i, rule in enumerate(rules["rules"]):
        if rule["id"] in seen:
            problems.append(f"rules/{i}/id: duplicate rule id {rule['id']!r}")
        seen.add(rule["id"])
    return problems


OWNER_OF = {name: spec["x-owner"] for name, spec in SCHEMAS["state"]["properties"].items()}


def check_state(state: dict, written_by) -> list[str]:
    problems = []
    for agent, fields in (written_by or {}).items():
        for name in fields:
            owner = OWNER_OF.get(name)
            if owner is None:
                problems.append(f"{agent} wrote {name!r}, which is not a state field")
            elif owner != agent:
                problems.append(f"{agent} wrote {name!r}, which is owned by {owner}")
    for i, c in enumerate(state.get("candidate_findings", [])):
        problems += check_confidence(f"candidate_findings/{i}/confidence", c["confidence"])
    if "handoff_log" in state and "counters" in state:
        log, steps = state["handoff_log"], state["counters"]["steps"]
        if len(log) != steps:
            problems.append(f"handoff_log has {len(log)} entries but counters/steps is {steps}")
        if [e["step"] for e in log] != list(range(1, len(log) + 1)):
            problems.append("handoff_log steps are not 1, 2, 3, ... in order")
    return problems


def check_apply_patch(payload: dict, ctx: dict) -> list[str]:
    args = payload["arguments"]
    return check_patch_diff("arguments/patch_diff", args["patch_diff"], args["workspace"], ctx.get("original_root"))


def run_checks(kind: str, payload, ctx: dict) -> tuple[list[str], list[str]]:
    schema = schema_errors(kind, payload)
    code: list[str] = []
    if not schema:
        if kind == "rules":
            code = check_rules(payload)
        elif kind == "output":
            code = check_output(payload, ctx)
        elif kind == "state":
            code = check_state(payload, ctx.get("written_by"))
        elif kind == "tool_apply_patch":
            code = check_apply_patch(payload, ctx)
    return schema, code


# --------------------------------------------------------------------------- self checks
def self_checks() -> list[str]:
    problems = []
    for name, schema in SCHEMAS.items():
        try:
            Draft202012Validator.check_schema(schema)
        except Exception as exc:  # noqa: BLE001 - report any metaschema failure
            problems.append(f"{name}.schema.json is not a valid schema: {_short(exc)}")
    for tool in TOOLS:
        if f"tool_{tool}" not in SCHEMAS:
            problems.append(f"missing schema for tool {tool}")
    rule_ids = [r["id"] for r in json.loads((GOLDEN / "rules.json").read_text(encoding="utf-8"))["rules"]]
    enum = SCHEMAS["output"]["$defs"]["ruleId"]["enum"]
    if sorted(enum) != sorted(rule_ids):
        problems.append(f"output.schema.json rule_id enum {enum} differs from golden/rules.json ids {rule_ids}")
    for name, spec in SCHEMAS["state"]["properties"].items():
        if spec.get("x-owner") not in OWNERS:
            problems.append(f"state field {name!r} has no valid x-owner")
    return problems


# --------------------------------------------------------------------------- fixtures
NOW = "2025-01-01T00:00:00Z"
CASE_01, CASE_04, CASE_10 = "case_01_sqli_fstring", "case_04_safe_sql_lookalike", "case_10_secret_and_personal_data"
USERS_CODE = '''query = f"SELECT id, name FROM users WHERE name = '{name}'"'''
CUSTOMERS_CODE = '''query = f"SELECT id, name FROM customers WHERE email = '{email}'"'''
USERS_DIFF = """--- a/src/users.py
+++ b/src/users.py
@@ -1,3 +1,3 @@
 def find_user(conn, name):
-    query = f"SELECT id, name FROM users WHERE name = '{name}'"
-    return conn.execute(query).fetchone()
+    query = "SELECT id, name FROM users WHERE name = ?"
+    return conn.execute(query, (name,)).fetchone()
"""
CUSTOMERS_DIFF = USERS_DIFF.replace("src/users.py", "src/customers.py")
OUTSIDE_DIFF = USERS_DIFF.replace("+++ b/src/users.py", "+++ b/../outside.py")
RULES_JSON = json.loads((GOLDEN / "rules.json").read_text(encoding="utf-8"))
RULES_VERSION = "sha256:" + hashlib.sha256((GOLDEN / "rules.json").read_bytes()).hexdigest()
INPUT_OK = {"source_folder": "golden/" + CASE_01, "rules_file": "golden/rules.json",
            "policy": {"file_cap": 200, "max_retries": 1, "test_command": "python -m unittest discover -s tests",
                       "ai_call_cap": 60, "time_cap_seconds": 1200, "confidence_gate": 0.7}}


@dataclass
class Case:
    kind: str
    name: str
    payload: object
    valid: bool
    layer: str = ""            # for invalid payloads: "schema" or "code" must reject it
    ctx: dict = field(default_factory=dict)


def entry(seq=1, event="run_started", actor="orchestrator", finding_id=None):
    return {"seq": seq, "timestamp": NOW, "actor": actor, "event": event, "finding_id": finding_id,
            "detail": "fake data run"}


def make_finding(fid, rule, file, line, code, status, **over):
    f = {"finding_id": fid, "rule_id": rule, "file": file, "line": line, "severity": "high",
         "evidence": {"file": file, "line": line, "quoted_code": code}, "confidence": 0.9, "detected_by": "rule",
         "status": status, "patch_diff": None, "tests": {"before": "pass", "after": None}, "recheck": "not_run",
         "residual_risk": "Only the existing tests cover the changed behaviour."}
    f.update(over)
    return f


def verified(fid, rule, file, line, code, diff):
    return make_finding(fid, rule, file, line, code, "verified_awaiting_approval", patch_diff=diff,
                        tests={"before": "pass", "after": "pass"}, recheck="clear")


def make_output(findings, hidden=0):
    def n(status):
        return sum(1 for f in findings if f["status"] == status)

    return {"outcome": "findings_reported" if findings else "safe_nothing_to_report",
            "run": {"rules_file_version": RULES_VERSION,
                    "ai_model": {"name": "fake-model", "version": "0.0", "endpoint": "fake://localhost"},
                    "sensitive_items_hidden": hidden, "tokens": {"input": 12000, "output": 900}},
            "totals": {"found": len(findings), "fixed_and_verified": n("verified_awaiting_approval"),
                       "rejected": n("rejected"), "needs_a_person": n("needs_a_person"),
                       "remaining": n("not_processed")},
            "findings": findings, "approvals": [], "audit_log": [entry()]}


def ok(result):
    return {"ok": True, "result": result}


def err(code, handling, **extra):
    return {"ok": False, "error": {"code": code, "message": "fake failure", "handling": handling, **extra}}


def tool(name, arguments, response):
    return {"tool": name, "arguments": arguments, "response": response}


def candidate(fid="F001", rank=1):
    return {"finding_id": fid, "rule_id": "SQLI", "file": "src/users.py", "line": 2, "severity": "high",
            "evidence": {"file": "src/users.py", "line": 2, "quoted_code": USERS_CODE}, "confidence": 0.9,
            "detected_by": "rule", "rank": rank}


def build_cases(tmp: Path) -> list[Case]:
    def copy_case(name):
        dest = tmp / name
        shutil.copytree(GOLDEN / name, dest, ignore=shutil.ignore_patterns("__pycache__"))
        return dest

    orig01, ws01 = GOLDEN / CASE_01, copy_case(CASE_01)
    orig04, ws04 = GOLDEN / CASE_04, copy_case(CASE_04)
    orig10, ws10 = GOLDEN / CASE_10, copy_case(CASE_10)
    c: list[Case] = []

    # ---- input.schema.json
    minimal = {"source_folder": "proj", "rules_file": "rules.json",
               "policy": {"file_cap": 1, "max_retries": 0, "test_command": "python -m pytest", "ai_call_cap": 1,
                          "time_cap_seconds": 1, "confidence_gate": 0}}
    caps = copy.deepcopy(INPUT_OK)
    caps["policy"].update({"step_cap": 50, "token_cap_input": 400000, "token_cap_output": 60000})
    no_cmd = copy.deepcopy(INPUT_OK); del no_cmd["policy"]["test_command"]
    gate = copy.deepcopy(INPUT_OK); gate["policy"]["confidence_gate"] = 1.5
    text_cap = copy.deepcopy(INPUT_OK); text_cap["policy"]["file_cap"] = "200"
    c += [Case("input", "agents_md_defaults", INPUT_OK, True), Case("input", "smallest_allowed_values", minimal, True),
          Case("input", "with_step_and_token_caps", caps, True),
          Case("input", "missing_test_command", no_cmd, False, "schema"),
          Case("input", "confidence_gate_1.5", gate, False, "schema"),
          Case("input", "file_cap_is_text", text_cap, False, "schema")]

    # ---- rules.schema.json
    one_rule = {"rules": [{"id": "SQLI", "severity": "high", "fix_allowed": True, "detect": "x"}]}
    dep = {"rules": [{"id": "DEP-PIN", "severity": "medium", "fix_allowed": False, "detect": "x",
                      "min_versions": {"requests": "2.31.0", "flask": "3.0"}}]}
    no_fix = copy.deepcopy(one_rule); del no_fix["rules"][0]["fix_allowed"]
    bad_sev = copy.deepcopy(one_rule); bad_sev["rules"][0]["severity"] = "critical"
    dup = copy.deepcopy(one_rule); dup["rules"].append(copy.deepcopy(dup["rules"][0]))
    c += [Case("rules", "golden_rules_json", RULES_JSON, True), Case("rules", "one_rule", one_rule, True),
          Case("rules", "dep_pin_with_min_versions", dep, True),
          Case("rules", "missing_fix_allowed", no_fix, False, "schema"),
          Case("rules", "severity_critical", bad_sev, False, "schema"),
          Case("rules", "duplicate_rule_id", dup, False, "code")]

    # ---- output.schema.json
    v1 = make_output([verified("F001", "SQLI", "src/users.py", 2, USERS_CODE, USERS_DIFF)])
    secret = make_finding("F002", "SECRET", "src/config.py", 1, 'API_KEY = "<SECRET_1>"', "needs_a_person",
                          reason="fix not allowed")
    v2 = make_output([verified("F001", "SQLI", "src/customers.py", 2, CUSTOMERS_CODE, CUSTOMERS_DIFF), secret], 3)
    v3 = make_output([])
    bad_quote = copy.deepcopy(v1)
    bad_quote["findings"][0]["evidence"]["quoted_code"] = "return conn.execute(query).fetchone()"
    nan_conf = copy.deepcopy(v1); nan_conf["findings"][0]["confidence"] = float("nan")
    escape = copy.deepcopy(v1); escape["findings"][0]["patch_diff"] = OUTSIDE_DIFF
    c += [Case("output", "case_01_verified_fix", v1, True, ctx={"project_root": orig01, "workspace": ws01}),
          Case("output", "case_10_fix_plus_secret", v2, True, ctx={"project_root": orig10, "workspace": ws10}),
          Case("output", "case_04_safe_nothing_to_report", v3, True, ctx={"project_root": orig04, "workspace": ws04}),
          Case("output", "quoted_code_not_on_that_line", bad_quote, False, "code",
               {"project_root": orig01, "workspace": ws01}),
          Case("output", "confidence_is_nan", nan_conf, False, "code", {"project_root": orig01, "workspace": ws01}),
          Case("output", "patch_diff_leaves_the_copy", escape, False, "code",
               {"project_root": orig01, "workspace": ws01})]

    # ---- tool schemas (canvas section 9)
    root = "golden/" + CASE_01
    c += [  # list_files
        Case("tool_list_files", "listing", tool("list_files", {"root": root, "file_cap": 200}, ok(
            {"files": ["src/users.py", "tests/test_users.py"], "skipped_dirs": [".git"], "truncated": False})), True),
        Case("tool_list_files", "cut_short_by_cap", tool("list_files", {"root": root, "file_cap": 1}, ok(
            {"files": ["src/users.py"], "skipped_dirs": [], "truncated": True})), True),
        Case("tool_list_files", "folder_not_found", tool("list_files", {"root": "nope", "file_cap": 5},
                                                          err("folder_not_found", "stop_run")), True),
        Case("tool_list_files", "missing_file_cap", tool("list_files", {"root": root}, ok(
            {"files": [], "skipped_dirs": [], "truncated": False})), False, "schema"),
        Case("tool_list_files", "listed_path_climbs_out", tool("list_files", {"root": root, "file_cap": 5}, ok(
            {"files": ["../secret.txt"], "skipped_dirs": [], "truncated": False})), False, "schema"),
        Case("tool_list_files", "failure_with_wrong_handling", tool("list_files", {"root": root, "file_cap": 5},
                                                                     err("folder_not_found", "skip_file_and_note")), False, "schema"),
        # read_file
        Case("tool_read_file", "reads_a_file", tool("read_file", {"root": root, "path": "src/users.py"}, ok(
            {"path": "src/users.py", "content": "x = 1\n", "line_count": 1})), True),
        Case("tool_read_file", "empty_file", tool("read_file", {"root": root, "path": "src/__init__.py"}, ok(
            {"path": "src/__init__.py", "content": "", "line_count": 0})), True),
        Case("tool_read_file", "file_not_found_skips", tool("read_file", {"root": root, "path": "src/x.py"},
                                                            err("file_not_found", "skip_file_and_note")), True),
        Case("tool_read_file", "absolute_path", tool("read_file", {"root": root, "path": "/etc/passwd"}, ok(
            {"path": "etc/passwd", "content": "", "line_count": 0})), False, "schema"),
        Case("tool_read_file", "success_without_line_count", tool("read_file", {"root": root, "path": "src/users.py"}, ok(
            {"path": "src/users.py", "content": "x"})), False, "schema"),
        Case("tool_read_file", "unknown_error_code", tool("read_file", {"root": root, "path": "src/users.py"},
                                                          err("disk_on_fire", "skip_file_and_note")), False, "schema"),
        # run_security_rules
        Case("tool_run_security_rules", "one_match", tool("run_security_rules", {
            "root": root, "rules_file": "golden/rules.json", "files": ["src/users.py"]}, ok(
            {"matches": [{"rule_id": "SQLI", "file": "src/users.py", "line": 2, "quoted_code": USERS_CODE}],
             "skipped_rules": []})), True),
        Case("tool_run_security_rules", "no_match_one_rule_skipped", tool("run_security_rules", {
            "root": root, "rules_file": "golden/rules.json", "files": ["src/users.py"]}, ok(
            {"matches": [], "skipped_rules": [{"rule_id": "PATH", "reason": "bad pattern"}]})), True),
        Case("tool_run_security_rules", "all_rules_failed", tool("run_security_rules", {
            "root": root, "rules_file": "golden/rules.json", "files": ["src/users.py"]},
            err("all_rules_failed", "skip_rule_and_note")), True),
        Case("tool_run_security_rules", "empty_file_list", tool("run_security_rules", {
            "root": root, "rules_file": "golden/rules.json", "files": []}, ok({"matches": [], "skipped_rules": []})),
             False, "schema"),
        Case("tool_run_security_rules", "quoted_code_has_two_lines", tool("run_security_rules", {
            "root": root, "rules_file": "golden/rules.json", "files": ["src/users.py"]}, ok(
            {"matches": [{"rule_id": "SQLI", "file": "src/users.py", "line": 2, "quoted_code": "a\nb"}],
             "skipped_rules": []})), False, "schema"),
        Case("tool_run_security_rules", "match_on_line_0", tool("run_security_rules", {
            "root": root, "rules_file": "golden/rules.json", "files": ["src/users.py"]}, ok(
            {"matches": [{"rule_id": "SQLI", "file": "src/users.py", "line": 0, "quoted_code": "x"}],
             "skipped_rules": []})), False, "schema"),
        # read_code_structure
        Case("tool_read_code_structure", "one_function", tool("read_code_structure", {
            "root": root, "files": ["src/users.py"]}, ok({"functions": [
                {"file": "src/users.py", "name": "find_user", "start_line": 1, "end_line": 3,
                 "calls": [{"name": "execute", "line": 3}]}], "unparsed_files": []})), True),
        Case("tool_read_code_structure", "one_file_unparsed", tool("read_code_structure", {
            "root": root, "files": ["src/bad.py"]}, ok(
            {"functions": [], "unparsed_files": [{"file": "src/bad.py", "reason": "syntax error"}]})), True),
        Case("tool_read_code_structure", "parse_error_hands_over", tool("read_code_structure", {
            "root": root, "files": ["src/bad.py"]}, err("parse_error", "hand_to_person")), True),
        Case("tool_read_code_structure", "no_files", tool("read_code_structure", {"root": root, "files": []}, ok(
            {"functions": [], "unparsed_files": []})), False, "schema"),
        Case("tool_read_code_structure", "function_without_calls", tool("read_code_structure", {
            "root": root, "files": ["src/users.py"]}, ok({"functions": [
                {"file": "src/users.py", "name": "find_user", "start_line": 1, "end_line": 3}],
                "unparsed_files": []})), False, "schema"),
        Case("tool_read_code_structure", "failure_with_wrong_handling", tool("read_code_structure", {
            "root": root, "files": ["src/users.py"]}, err("parse_error", "stop_run")), False, "schema"),
        # apply_patch (code checks use the real temporary copy)
        Case("tool_apply_patch", "patch_inside_copy", tool("apply_patch", {"workspace": str(ws01), "patch_diff": USERS_DIFF}, ok(
            {"applied": True, "files_changed": ["src/users.py"], "syntax_valid": True})), True,
             ctx={"original_root": orig01}),
        Case("tool_apply_patch", "second_patch_inside_copy", tool("apply_patch", {
            "workspace": str(ws10), "patch_diff": CUSTOMERS_DIFF}, ok(
            {"applied": True, "files_changed": ["src/customers.py"], "syntax_valid": True})), True,
             ctx={"original_root": orig10}),
        Case("tool_apply_patch", "syntax_invalid_undone", tool("apply_patch", {
            "workspace": str(ws01), "patch_diff": USERS_DIFF}, err("syntax_invalid", "undo_change",
                                                                    change_undone=True)), True,
             ctx={"original_root": orig01}),
        Case("tool_apply_patch", "patch_leaves_the_copy", tool("apply_patch", {
            "workspace": str(ws01), "patch_diff": OUTSIDE_DIFF}, ok(
            {"applied": True, "files_changed": ["src/users.py"], "syntax_valid": True})), False, "code",
             {"original_root": orig01}),
        Case("tool_apply_patch", "workspace_is_the_original", tool("apply_patch", {
            "workspace": str(orig01), "patch_diff": USERS_DIFF}, ok(
            {"applied": True, "files_changed": ["src/users.py"], "syntax_valid": True})), False, "code",
             {"original_root": orig01}),
        Case("tool_apply_patch", "failure_not_undone", tool("apply_patch", {
            "workspace": str(ws01), "patch_diff": USERS_DIFF}, err("patch_does_not_apply", "undo_change",
                                                                    change_undone=False)), False, "schema",
             {"original_root": orig01}),
        # run_tests
        Case("tool_run_tests", "tests_pass", tool("run_tests", {
            "workspace": str(ws01), "test_command": "python -m unittest discover -s tests", "timeout_seconds": 60}, ok(
            {"outcome": "pass", "exit_code": 0, "duration_seconds": 0.2, "output_tail": "OK"})), True),
        Case("tool_run_tests", "tests_fail", tool("run_tests", {
            "workspace": str(ws01), "test_command": "python -m unittest discover -s tests", "timeout_seconds": 60}, ok(
            {"outcome": "fail", "exit_code": 1, "duration_seconds": 0.2, "output_tail": "FAILED"})), True),
        Case("tool_run_tests", "no_tests", tool("run_tests", {
            "workspace": str(ws01), "test_command": "python -m unittest discover -s tests", "timeout_seconds": 60}, ok(
            {"outcome": "none", "exit_code": None, "duration_seconds": 0.0, "output_tail": ""})), True),
        Case("tool_run_tests", "pass_with_exit_1", tool("run_tests", {
            "workspace": str(ws01), "test_command": "python -m unittest", "timeout_seconds": 60}, ok(
            {"outcome": "pass", "exit_code": 1, "duration_seconds": 0.2, "output_tail": "OK"})), False, "schema"),
        Case("tool_run_tests", "timeout_0", tool("run_tests", {
            "workspace": str(ws01), "test_command": "python -m unittest", "timeout_seconds": 0}, ok(
            {"outcome": "pass", "exit_code": 0, "duration_seconds": 0.2, "output_tail": "OK"})), False, "schema"),
        Case("tool_run_tests", "unknown_error_code", tool("run_tests", {
            "workspace": str(ws01), "test_command": "python -m unittest", "timeout_seconds": 60},
            err("out_of_coffee", "not_verified_tell_person")), False, "schema"),
        # request_recheck
        Case("tool_request_recheck", "clear", tool("request_recheck", {"workspace": str(ws01), "files": ["src/users.py"]}, ok(
            {"clear": True, "files_checked": ["src/users.py"], "matches": []})), True),
        Case("tool_request_recheck", "not_clear_one_match", tool("request_recheck", {
            "workspace": str(ws01), "files": ["src/users.py"]}, ok(
            {"clear": False, "files_checked": ["src/users.py"],
             "matches": [{"rule_id": "SQLI", "file": "src/users.py", "line": 2, "quoted_code": USERS_CODE}]})), True),
        Case("tool_request_recheck", "auditor_failed", tool("request_recheck", {
            "workspace": str(ws01), "files": ["src/users.py"]}, err("auditor_failed", "not_verified")), True),
        Case("tool_request_recheck", "clear_but_matches_left", tool("request_recheck", {
            "workspace": str(ws01), "files": ["src/users.py"]}, ok(
            {"clear": True, "files_checked": ["src/users.py"],
             "matches": [{"rule_id": "SQLI", "file": "src/users.py", "line": 2, "quoted_code": USERS_CODE}]})),
             False, "schema"),
        Case("tool_request_recheck", "not_clear_but_no_matches", tool("request_recheck", {
            "workspace": str(ws01), "files": ["src/users.py"]}, ok(
            {"clear": False, "files_checked": ["src/users.py"], "matches": []})), False, "schema"),
        Case("tool_request_recheck", "no_files", tool("request_recheck", {"workspace": str(ws01), "files": []}, ok(
            {"clear": True, "files_checked": ["src/users.py"], "matches": []})), False, "schema"),
    ]

    # ---- state.schema.json
    s1 = {"run_id": "run-001", "input": INPUT_OK}
    s2 = {"run_id": "run-002", "input": INPUT_OK, "rules": RULES_JSON, "rules_file_version": RULES_VERSION,
          "workspace": {"path": str(ws01), "original_root": str(orig01)},
          "counters": {"steps": 1, "ai_calls": 0, "tokens": {"input": 0, "output": 0}, "elapsed_seconds": 1.5},
          "file_list": {"files": ["src/users.py"], "skipped_dirs": [], "truncated": False},
          "candidate_findings": [candidate()]}
    s3 = copy.deepcopy(s2)
    s3.update({
        "run_id": "run-003",
        "investigations": [{"finding_id": "F001", "traced_cause": {"explanation": "name reaches an f-string",
                                                                    "path": ["src/users.py"]},
                            "fix_approach": "use a ? placeholder", "fixable": True, "handoff_reason": None}],
        "baseline_tests": {"outcome": "pass", "exit_code": 0},
        "fix_attempts": [{"finding_id": "F001", "attempt": 1, "patch_diff": USERS_DIFF,
                          "files_changed": ["src/users.py"], "tests": {"before": "pass", "after": "pass"},
                          "recheck": "clear", "decision": "keep", "residual_risk": "Tests cover this path only."}],
        "recheck_results": [{"finding_id": "F001", "attempt": 1, "clear": True, "matches": []}],
        "finding_status": [{"finding_id": "F001", "status": "verified_awaiting_approval", "reason": None}]})
    with_status = copy.deepcopy(s2); with_status["candidate_findings"][0]["status"] = "needs_a_person"
    bad_id = {"run_id": "7"}
    log_entry = {"step": 1, "timestamp": NOW, "agent": "auditor", "job": "audit", "finding_id": None,
                 "wrote": ["file_list", "candidate_findings"], "result": "ok"}
    with_log = copy.deepcopy(s2); with_log["handoff_log"] = [log_entry]
    log_short = copy.deepcopy(s2); log_short["handoff_log"] = []
    log_bad_agent = copy.deepcopy(with_log); log_bad_agent["handoff_log"][0]["agent"] = "orchestrator"
    c += [Case("state", "handoff_log_matches_steps", with_log, True),
          Case("state", "handoff_log_shorter_than_steps", log_short, False, "code"),
          Case("state", "handoff_log_agent_is_not_an_agent", log_bad_agent, False, "schema"),
          Case("state", "just_started", s1, True),
          Case("state", "after_auditor", s2, True, ctx={"written_by": {
              "orchestrator": ["run_id", "input", "rules", "workspace", "counters"],
              "auditor": ["file_list", "candidate_findings"]}}),
          Case("state", "after_fixer", s3, True, ctx={"written_by": {
              "investigator": ["investigations"], "fixer_validator": ["baseline_tests", "fix_attempts"],
              "auditor": ["recheck_results"], "orchestrator": ["finding_status"]}}),
          Case("state", "bad_run_id_and_no_input", bad_id, False, "schema"),
          Case("state", "auditor_sets_a_status", with_status, False, "schema"),
          Case("state", "auditor_writes_fix_attempts", s3, False, "code",
               {"written_by": {"auditor": ["file_list", "fix_attempts"]}})]
    return c


# --------------------------------------------------------------------------- runner
KIND_ORDER = ["input", "rules", "output"] + [f"tool_{t}" for t in TOOLS] + ["state"]


def main() -> int:
    sys.stdout.reconfigure(errors="replace")
    failures = 0
    print("Self checks")
    problems = self_checks()
    for p in problems:
        print(f"  FAIL  {p}")
    print("  ok    all schemas valid, 7 tool schemas present, rule_id enum matches golden/rules.json, "
          "every state field has an owner" if not problems else "")
    failures += len(problems)

    total = 0
    with tempfile.TemporaryDirectory() as tmp:
        cases = build_cases(Path(tmp))
        for kind in KIND_ORDER:
            mine = [x for x in cases if x.kind == kind]
            print(f"\n{kind}.schema.json")
            for case in mine:
                total += 1
                schema, code = run_checks(case.kind, case.payload, case.ctx)
                rejected_by = "schema" if schema else ("code" if code else "")
                messages = (schema or code)[:2]
                if case.valid:
                    good = not rejected_by
                    print(f"  valid    {'ok      ' if good else 'WRONG   '} {case.name}")
                    if not good:
                        print(f"             rejected by {rejected_by}: {'; '.join(messages)}")
                else:
                    good = rejected_by == case.layer
                    verdict = "rejected" if good else "WRONG   "
                    print(f"  invalid  {verdict} {case.name}  [{rejected_by or 'ACCEPTED'}]")
                    for m in messages:
                        print(f"             - {m}")
                    if not good:
                        print(f"             expected rejection by {case.layer}")
                failures += 0 if good else 1
    print(f"\n{total - (failures - len(problems))}/{total} payloads behaved as expected"
          f"{'' if not problems else f', {len(problems)} self-check problem(s)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
