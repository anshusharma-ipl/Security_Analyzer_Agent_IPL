"""apply_patch: apply a unified diff to the temporary copy (changes the copy only).
Used by: Fixer & Validator.

Rules, all enforced in code:
  - the workspace must be a temporary copy registered by make_temp_copy; the original
    folder (or any other folder) is refused;
  - every file in the diff is resolved with realpath and must stay inside the copy;
    links that leave the copy are refused;
  - only existing .py files may change: no new files, no deletes, no renames, and nothing
    that changes packages (requirements.txt and the like);
  - the whole diff is applied in memory first and must match the file text exactly;
  - after writing, every changed file must parse as Python; if any does not, or anything
    fails while writing, every file is restored byte for byte and an error is returned.
A refused or failed patch leaves the copy unchanged (change_undone is always true).
"""
from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import _schema
from ._safety import SafetyError, is_link, resolve_inside
from ._workspace import require_temp_copy

TOOL = "apply_patch"
HANDLING = "undo_change"
_HUNK = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


class PatchError(ValueError):
    """The diff is malformed or does not match the files. ``code`` is the schema error code."""

    def __init__(self, message: str, code: str = "patch_does_not_apply") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class _FilePatch:
    path: str
    hunks: list[tuple[int, list[tuple[str, str]]]] = field(default_factory=list)  # (old_start, [(op, text)])


def _clean(path: str) -> str:
    path = path.split("\t")[0].strip()
    return path[2:] if path[:2] in ("a/", "b/") else path


def _parse(diff: str) -> list[_FilePatch]:
    lines = diff.replace("\r\n", "\n").split("\n")
    patches: list[_FilePatch] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith(("rename ", "copy ", "deleted file", "new file", "old mode", "new mode")):
            raise PatchError(f"unsupported change in the diff ({line.split()[0]}): only edits to existing files are allowed")
        if line.startswith("--- "):
            if i + 1 >= len(lines) or not lines[i + 1].startswith("+++ "):
                raise PatchError("'---' line is not followed by a '+++' line")
            old, new = line[4:].split("\t")[0].strip(), lines[i + 1][4:].split("\t")[0].strip()
            if old == "/dev/null":
                raise PatchError("the diff creates a new file; only edits to existing files are allowed")
            if new == "/dev/null":
                raise PatchError("the diff deletes a file; deleting files is never allowed")
            if _clean(old) != _clean(new):
                raise PatchError(f"the diff renames {_clean(old)!r} to {_clean(new)!r}; renames are not allowed")
            patch = _FilePatch(_clean(new))
            patches.append(patch)
            i += 2
            while i < len(lines) and lines[i].startswith("@@"):
                m = _HUNK.match(lines[i])
                if not m:
                    raise PatchError(f"bad hunk header: {lines[i]!r}")
                old_start, old_len = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
                new_len = int(m.group(4) if m.group(4) is not None else 1)
                i += 1
                body: list[tuple[str, str]] = []
                seen_old = seen_new = 0
                while i < len(lines) and (seen_old < old_len or seen_new < new_len):
                    text = lines[i]
                    if text.startswith("\\"):          # "\ No newline at end of file"
                        i += 1
                        continue
                    op, content = (text[:1] or " "), text[1:]
                    if op not in " -+":
                        raise PatchError(f"unexpected line inside a hunk: {text!r}")
                    body.append((op, content))
                    seen_old += op in " -"
                    seen_new += op in " +"
                    i += 1
                while i < len(lines) and lines[i].startswith("\\"):
                    i += 1
                if (seen_old, seen_new) != (old_len, new_len):
                    raise PatchError(f"hunk at line {old_start} is shorter than its header says")
                patch.hunks.append((old_start, body))
            if not patch.hunks:
                raise PatchError(f"{patch.path!r} has no hunks")
            continue
        i += 1
    if not patches:
        raise PatchError("no file headers ('--- a/file' and '+++ b/file') found in the diff")
    return patches


def _apply(path: str, text: str, patch: _FilePatch) -> str:
    """Return the patched text, or raise PatchError if a hunk does not match."""
    eol = "\r\n" if "\r\n" in text else "\n"
    old_lines = text.splitlines()
    out: list[str] = []
    cursor = 0
    for old_start, body in patch.hunks:
        expected = [c for op, c in body if op in " -"]
        start = max(old_start - 1, 0)
        if old_lines[start:start + len(expected)] != expected:
            hits = [p for p in range(len(old_lines) - len(expected) + 1) if old_lines[p:p + len(expected)] == expected]
            if len(hits) != 1:
                raise PatchError(f"hunk at line {old_start} of {path!r} does not match the file")
            start = hits[0]
        if start < cursor:
            raise PatchError(f"hunks of {path!r} overlap or are out of order")
        out += old_lines[cursor:start]
        out += [c for op, c in body if op in " +"]
        cursor = start + len(expected)
    out += old_lines[cursor:]
    return eol.join(out) + (eol if text.endswith(("\n", "\r\n")) or not text else "")


def apply_patch(workspace: str, patch_diff: str) -> dict:
    args = {"workspace": workspace, "patch_diff": patch_diff}
    _schema.validate_args(TOOL, args)

    def refuse(code: str, message: str) -> dict:
        return _schema.fail(TOOL, args, code, message, HANDLING, change_undone=True)

    if not os.path.isdir(workspace):
        return refuse("workspace_not_found", f"workspace {workspace!r} is not a folder")
    try:
        require_temp_copy(workspace)
    except SafetyError as exc:
        return refuse("outside_workspace", str(exc))

    try:
        patches = _parse(patch_diff)
        originals: dict[str, bytes] = {}
        updated: dict[str, str] = {}
        for patch in patches:
            if patch.path in updated:
                raise PatchError(f"{patch.path!r} appears twice in the diff")
            if not patch.path.endswith(".py"):
                raise PatchError(f"{patch.path!r} is not a .py file; only Python source may be patched "
                                 "(package files such as requirements.txt are never changed)")
            try:
                full = resolve_inside(workspace, patch.path)
            except SafetyError as exc:
                return refuse("outside_workspace", str(exc))
            if is_link(full) or not os.path.isfile(full):
                raise PatchError(f"{patch.path!r} is not an existing regular file in the temporary copy")
            raw = Path(full).read_bytes()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                raise PatchError(f"{patch.path!r} is not valid UTF-8 text") from None
            originals[full] = raw
            updated[full] = _apply(patch.path, text, patch)
    except PatchError as exc:
        return refuse(exc.code, str(exc))

    written: list[str] = []
    try:
        for full, new_text in updated.items():
            Path(full).write_bytes(new_text.encode("utf-8"))
            written.append(full)
        for full in updated:
            try:
                ast.parse(Path(full).read_text(encoding="utf-8"), filename=full)
            except SyntaxError as exc:
                raise PatchError(f"{os.path.relpath(full, workspace)!r} no longer parses as Python "
                                 f"(line {exc.lineno}: {exc.msg}); the change was undone", "syntax_invalid") from None
    except (PatchError, OSError) as exc:
        for full in written:
            Path(full).write_bytes(originals[full])
        code = exc.code if isinstance(exc, PatchError) else "patch_does_not_apply"
        return refuse(code, str(exc) if isinstance(exc, PatchError) else f"could not write: {exc}; the change was undone")

    changed = sorted(os.path.relpath(full, os.path.realpath(workspace)).replace(os.sep, "/") for full in updated)
    return _schema.ok(TOOL, args, {"applied": True, "files_changed": changed, "syntax_valid": True})
