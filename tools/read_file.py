"""read_file: read one source file (reads only). Used by: Auditor, Investigator.

The path must resolve (realpath) to a file inside the project. A symlink or junction
that leaves the project is refused. Failures skip the file and are noted by the caller.
Secrets, emails and phone numbers are replaced by <SECRET_n>, <EMAIL_n>, <PHONE_n> before the
text leaves the tool (AGENTS.md: nothing sensitive reaches a model). Line numbers are unchanged.
"""
from __future__ import annotations

import os

from . import _schema
from ._mask import Masker
from ._safety import SafetyError, resolve_inside

TOOL = "read_file"
HANDLING = "skip_file_and_note"


def read_file(root: str, path: str) -> dict:
    args = {"root": root, "path": path}
    _schema.validate_args(TOOL, args)

    try:
        full = resolve_inside(root, path)
    except SafetyError as exc:
        return _schema.fail(TOOL, args, "outside_project", str(exc), HANDLING)

    if not os.path.isfile(full):
        return _schema.fail(TOOL, args, "file_not_found", f"{path!r} is not a file in the project", HANDLING)

    try:
        with open(full, "rb") as handle:
            raw = handle.read()
    except PermissionError:
        return _schema.fail(TOOL, args, "permission_denied", f"cannot read {path!r}: permission denied", HANDLING)

    if b"\x00" in raw:
        return _schema.fail(TOOL, args, "not_text_file", f"{path!r} is a binary file", HANDLING)
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        return _schema.fail(TOOL, args, "not_text_file", f"{path!r} is not valid UTF-8 text", HANDLING)

    masker = Masker()
    hidden_content = "".join(masker.line(part) for part in content.splitlines(keepends=True))
    return _schema.ok(TOOL, args, {"path": path, "content": hidden_content, "line_count": len(content.splitlines()),
                                   "sensitive_items_hidden": masker.hidden})
