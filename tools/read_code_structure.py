"""read_code_structure: functions, what they call, and who calls them (reads only).
Used by: Investigator.

Uses Python's ast. Reports every function and method in the requested files with the calls
it makes (``calls``) and, across ALL requested files, the functions that call it (``callers``).
Callers are matched by simple name, so they are a lead for the Investigator, not proof.
Code outside any function is reported as the caller ``<module>``.
A file that does not parse goes in unparsed_files; the others are still read.
"""
from __future__ import annotations

import ast
import os
from pathlib import Path

from . import _schema
from ._safety import SafetyError, resolve_inside

TOOL = "read_code_structure"
HANDLING = "hand_to_person"


def _call_name(node: ast.Call) -> str | None:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


class _Collector(ast.NodeVisitor):
    def __init__(self, file: str) -> None:
        self.file = file
        self.stack: list[str] = []          # enclosing function names
        self.functions: list[dict] = []
        self.sites: list[dict] = []         # every call: who, where, what

    def _function(self, node) -> None:
        entry = {"file": self.file, "name": node.name, "start_line": node.lineno,
                 "end_line": node.end_lineno or node.lineno, "calls": []}
        self.functions.append(entry)
        self.stack.append(node.name)
        self.generic_visit(node)
        self.stack.pop()

    visit_FunctionDef = visit_AsyncFunctionDef = _function

    def visit_Call(self, node: ast.Call) -> None:
        name = _call_name(node)
        if name:
            caller = self.stack[-1] if self.stack else "<module>"
            self.sites.append({"file": self.file, "caller": caller, "callee": name, "line": node.lineno,
                               "depth": len(self.stack)})
        self.generic_visit(node)


def read_code_structure(root: str, files: list[str]) -> dict:
    args = {"root": root, "files": files}
    _schema.validate_args(TOOL, args)

    if not os.path.isdir(root):
        return _schema.fail(TOOL, args, "file_not_found", f"root {root!r} is not a folder", HANDLING)

    functions: list[dict] = []
    sites: list[dict] = []
    unparsed: list[dict] = []
    for rel in files:
        try:
            full = resolve_inside(root, rel)
        except SafetyError as exc:
            return _schema.fail(TOOL, args, "outside_project", str(exc), HANDLING)
        if not os.path.isfile(full):
            return _schema.fail(TOOL, args, "file_not_found", f"{rel!r} is not a file in the project", HANDLING)
        try:
            tree = ast.parse(Path(full).read_text(encoding="utf-8"), filename=rel)
        except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
            unparsed.append({"file": rel, "reason": f"cannot parse: {exc}"})
            continue
        collector = _Collector(rel)
        collector.visit(tree)
        functions += collector.functions
        sites += collector.sites

    # Attach calls (made inside each function) and callers (functions that call it).
    for fn in functions:
        own = [s for s in sites if s["file"] == fn["file"] and fn["start_line"] <= s["line"] <= fn["end_line"]
               and s["caller"] == fn["name"]]
        fn["calls"] = sorted(({"name": s["callee"], "line": s["line"]} for s in own), key=lambda c: (c["line"], c["name"]))
        callers = {(s["file"], s["caller"], s["line"]) for s in sites if s["callee"] == fn["name"]}
        fn["callers"] = [{"file": f, "function": c, "line": n} for f, c, n in sorted(callers)]

    functions.sort(key=lambda f: (f["file"], f["start_line"]))
    return _schema.ok(TOOL, args, {"functions": functions, "unparsed_files": unparsed})
