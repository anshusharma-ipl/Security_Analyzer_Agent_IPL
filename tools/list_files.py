"""list_files: list the project's files (reads only). Used by: Auditor.

Skips .git, node_modules, .venv and __pycache__. Never follows a symlink or junction:
a link is skipped and reported in skipped_dirs. Stops at file_cap and sets truncated=true
so the caller knows the list is incomplete.
"""
from __future__ import annotations

import os

from . import _schema
from ._safety import SKIP_DIRS, is_link

TOOL = "list_files"


def list_files(root: str, file_cap: int) -> dict:
    args = {"root": root, "file_cap": file_cap}
    _schema.validate_args(TOOL, args)

    if not os.path.exists(root):
        return _schema.fail(TOOL, args, "folder_not_found", f"folder {root!r} does not exist", "stop_run")
    if not os.path.isdir(root):
        return _schema.fail(TOOL, args, "not_a_directory", f"{root!r} is not a folder", "stop_run")

    root_real = os.path.realpath(root)
    files: list[str] = []
    skipped: set[str] = set()
    truncated = False

    def rel(path: str) -> str:
        return os.path.relpath(path, root_real).replace(os.sep, "/")

    pending = [root_real]
    try:
        while pending and not truncated:
            current = pending.pop()
            with os.scandir(current) as it:
                entries = sorted(it, key=lambda e: e.name)
            subfolders = []
            for entry in entries:
                if is_link(entry.path):
                    skipped.add(rel(entry.path))  # never followed, inside the project or not
                elif entry.is_dir(follow_symlinks=False):
                    if entry.name in SKIP_DIRS:
                        skipped.add(rel(entry.path))
                    else:
                        subfolders.append(entry.path)
                elif entry.is_file(follow_symlinks=False):
                    if len(files) >= file_cap:
                        truncated = True
                        break
                    files.append(rel(entry.path))
            pending.extend(reversed(subfolders))
    except PermissionError as exc:
        return _schema.fail(TOOL, args, "permission_denied", f"cannot read {exc.filename!r}: permission denied", "stop_run")

    return _schema.ok(TOOL, args, {"files": sorted(files), "skipped_dirs": sorted(skipped), "truncated": truncated})
