"""run_security_rules: apply text-pattern rules (reads only). Used by: Auditor.

Implements the six rules in golden/rules.json deterministically. No AI model.
  SQLI      SQL text built from a variable (f-string, + or %), then run. Found with ast so a
            SQL-looking log message that is never run is not reported.
  CMDI      shell=True, or os.system / os.popen with a command built from a variable.
  PATH      os.path.join with a non-literal part after the first and no realpath / resolve / commonpath check nearby.
  SECRET    a key or password written as a literal in the source.
  WEAKHASH  MD5 or SHA1 used.
  DEP-PIN   a package pinned below rule["min_versions"] in requirements.txt.
Every quoted_code has secrets, emails and phone numbers replaced by placeholders.
A rule that raises is skipped and listed in skipped_rules; an unreadable file in skipped_files.
"""
from __future__ import annotations

import ast
import json
import os
import re
from pathlib import Path

from . import _schema
from ._mask import Masker, secret_spans
from ._safety import SafetyError, is_link, resolve_inside

TOOL = "run_security_rules"
HANDLING = "skip_rule_and_note"

_SQL_WORD = re.compile(r"\b(?:select|insert|update|delete|replace|drop|create|alter)\b", re.IGNORECASE)
_SQL_START = re.compile(r"^\s*(?:select|insert\s+into|update|delete\s+from|replace\s+into|drop|create|alter|with)\b",
                        re.IGNORECASE)
_CMDI_SHELL = re.compile(r"\bshell\s*=\s*True\b")
_CMDI_OS = re.compile(r"\bos\.(?:system|popen)\s*\(\s*(?!['\"][^'\"]*['\"]\s*\))")
_PATH_JOIN = re.compile(r"\bos\.path\.join\s*\(")
_PATH_GUARD = re.compile(r"\b(?:realpath|resolve|abspath|commonpath|commonprefix|is_relative_to)\b")
_WEAKHASH = re.compile(r"\bhashlib\s*\.\s*(?:md5|sha1)\b|\bhashlib\s*\.\s*new\s*\(\s*['\"](?:md5|sha1)['\"]", re.IGNORECASE)
_PIN = re.compile(r"^\s*(?P<pkg>[A-Za-z0-9_.\-]+)\s*==\s*(?P<ver>[0-9]+(?:\.[0-9]+)*)")
_EXECUTE = {"execute", "executemany", "executescript"}


# --------------------------------------------------------------------------- SQLI via ast
def _static_text(node: ast.AST) -> str:
    """The literal pieces of a string expression, joined; variables become empty."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        return "".join(_static_text(v) for v in node.values)
    if isinstance(node, ast.BinOp):
        return _static_text(node.left) + _static_text(node.right)
    return ""


def _is_dynamic_sql(node: ast.AST) -> bool:
    """True for SQL text built from a variable with an f-string, '+' or '%'."""
    if isinstance(node, ast.JoinedStr):
        built = any(isinstance(v, ast.FormattedValue) for v in node.values)
    elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        built = not (isinstance(node.left, ast.Constant) and isinstance(node.right, ast.Constant))
    elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format":
        built = isinstance(node.func.value, ast.Constant)
    else:
        return False
    text = _static_text(node.func.value) if isinstance(node, ast.Call) else _static_text(node)
    return built and bool(_SQL_WORD.search(text))


def _sqli_lines(tree: ast.AST) -> list[int]:
    """Lines where dynamic SQL text is built and then run (directly or through a variable)."""
    found: set[int] = set()
    scopes = [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Module))]
    for scope in scopes:
        built: dict[str, int] = {}  # variable name -> line where dynamic SQL was assigned
        calls: list[ast.Call] = []
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign) and _is_dynamic_sql(node.value):
                for target in node.targets:
                    if isinstance(target, ast.Name):
                        built[target.id] = node.value.lineno
            elif isinstance(node, ast.Call):
                calls.append(node)
        for call in calls:
            func = call.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name not in _EXECUTE or not call.args:
                continue
            arg = call.args[0]
            if _is_dynamic_sql(arg):
                found.add(arg.lineno)
            elif isinstance(arg, ast.Name) and arg.id in built:
                found.add(built[arg.id])
    # SQL built in a function and handed on (case_05: service.py builds, db.py runs).
    for scope in scopes:
        if not isinstance(scope, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for node in ast.walk(scope):
            if isinstance(node, ast.Assign) and _is_dynamic_sql(node.value) and _SQL_START.match(_static_text(node.value)):
                names = [t.id for t in node.targets if isinstance(t, ast.Name)]
                for call in (c for c in ast.walk(scope) if isinstance(c, ast.Call)):
                    passed = [a.id for a in call.args if isinstance(a, ast.Name)]
                    func = call.func
                    fname = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
                    if fname not in _EXECUTE and any(n in passed for n in names):
                        found.add(node.value.lineno)
    return sorted(found)


# --------------------------------------------------------------------------- the other rules
def _variable_join_lines(tree: ast.AST) -> set[int]:
    """Lines of os.path.join calls where a part after the first is not a fixed string. Joining only
    fixed strings (os.path.join(folder, "a.txt")) puts no user-given name onto the folder."""
    lines = set()
    for node in ast.walk(tree):
        f = node.func if isinstance(node, ast.Call) else None
        if (isinstance(f, ast.Attribute) and f.attr == "join" and isinstance(f.value, ast.Attribute)
                and f.value.attr == "path" and isinstance(f.value.value, ast.Name) and f.value.value.id == "os"
                and any(not (isinstance(a, ast.Constant) and isinstance(a.value, str)) for a in node.args[1:])):
            lines.add(node.lineno)
    return lines


def _version(text: str) -> tuple[int, ...]:
    return tuple(int(part) for part in text.split("."))


def _line_rules(rule_id: str, lines: list[str], joins: set[int] | None = None) -> list[int]:
    hits = []
    for number, line in enumerate(lines, 1):
        code = line.split("#", 1)[0] if rule_id != "SECRET" else line
        if not code.strip() or line.lstrip().startswith("#"):
            continue
        if rule_id == "CMDI" and (_CMDI_SHELL.search(code) or _CMDI_OS.search(code)):
            hits.append(number)
        elif rule_id == "PATH" and _PATH_JOIN.search(code) and (joins is None or number in joins):
            window = "\n".join(lines[max(0, number - 3): number + 4])
            if not _PATH_GUARD.search(window):
                hits.append(number)
        elif rule_id == "SECRET" and secret_spans(line):
            hits.append(number)
        elif rule_id == "WEAKHASH" and _WEAKHASH.search(code):
            hits.append(number)
    return hits


def _dep_pins(lines: list[str], min_versions: dict[str, str]) -> list[int]:
    norm = lambda name: re.sub(r"[-_.]+", "-", name).lower()  # noqa: E731
    wanted = {norm(k): v for k, v in min_versions.items()}
    hits = []
    for number, line in enumerate(lines, 1):
        m = _PIN.match(line)
        if m and norm(m.group("pkg")) in wanted and _version(m.group("ver")) < _version(wanted[norm(m.group("pkg"))]):
            hits.append(number)
    return hits


# --------------------------------------------------------------------------- the tool
def run_security_rules(root: str, rules_file: str, files: list[str]) -> dict:
    args = {"root": root, "rules_file": rules_file, "files": files}
    _schema.validate_args(TOOL, args)

    if not os.path.isdir(root):
        return _schema.fail(TOOL, args, "root_not_found", f"root {root!r} is not a folder", HANDLING)
    try:
        rules_doc = json.loads(Path(rules_file).read_text(encoding="utf-8"))
        _schema.validate_document("rules", rules_doc)
    except (OSError, ValueError) as exc:
        return _schema.fail(TOOL, args, "rules_file_unreadable", f"rules file {rules_file!r} cannot be used: {exc}", HANDLING)

    masker = Masker()
    matches: list[dict] = []
    skipped_rules: dict[str, str] = {}
    skipped_files: list[dict] = []
    ran = 0

    for rel in files:
        try:
            full = resolve_inside(root, rel)
        except SafetyError as exc:
            skipped_files.append({"file": rel, "reason": str(exc)})
            continue
        if not os.path.isfile(full):
            skipped_files.append({"file": rel, "reason": "not a file"})
            continue
        try:
            raw = Path(full).read_bytes()
            if b"\x00" in raw:
                skipped_files.append({"file": rel, "reason": "binary file"})
                continue
            text = raw.decode("utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            skipped_files.append({"file": rel, "reason": f"cannot read: {exc}"})
            continue
        lines = text.splitlines()
        is_py, is_req = rel.endswith(".py"), os.path.basename(rel) == "requirements.txt"
        tree = None
        if is_py:
            try:
                tree = ast.parse(text)
            except SyntaxError:
                skipped_files.append({"file": rel, "reason": "does not parse as Python; SQLI not checked"})

        for rule in rules_doc["rules"]:
            rid = rule["id"]
            try:
                if rid == "DEP-PIN":
                    hits = _dep_pins(lines, rule.get("min_versions", {})) if is_req else []
                elif not is_py:
                    hits = []
                elif rid == "SQLI":
                    hits = _sqli_lines(tree) if tree is not None else []
                elif rid in ("CMDI", "PATH", "SECRET", "WEAKHASH"):
                    hits = _line_rules(rid, lines, _variable_join_lines(tree) if tree is not None else None)
                else:
                    skipped_rules.setdefault(rid, "no pattern is implemented for this rule id")
                    continue
            except Exception as exc:  # noqa: BLE001 - a faulty rule is skipped, never fatal
                skipped_rules.setdefault(rid, f"rule failed: {exc}")
                continue
            ran += 1
            for number in hits:
                matches.append({"rule_id": rid, "file": rel, "line": number,
                                "quoted_code": masker.line(lines[number - 1].strip())})

    if files and ran == 0 and skipped_rules and not matches:
        return _schema.fail(TOOL, args, "all_rules_failed", "every rule failed: " + "; ".join(
            f"{k}: {v}" for k, v in skipped_rules.items()), HANDLING)
    matches.sort(key=lambda m: (m["file"], m["line"], m["rule_id"]))
    result = {"matches": matches, "skipped_rules": [{"rule_id": k, "reason": v} for k, v in skipped_rules.items()],
              "sensitive_items_hidden": masker.hidden}
    if skipped_files:
        result["skipped_files"] = skipped_files
    return _schema.ok(TOOL, args, result)
