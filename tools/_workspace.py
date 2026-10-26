"""Temporary-copy registry.

make_temp_copy (orchestrator helper) creates   <run_dir>/copy/        the project copy
                                                <run_dir>/workspace.json  this marker
The marker sits OUTSIDE the copy so it never shows up in a scan, a diff or a test run.

Tools that write or execute (apply_patch, run_tests) call require_temp_copy: a folder is
accepted only if its marker names it. That is a whitelist, so the original folder, or any
other folder, is refused without the tool having to know where the original is.
"""
from __future__ import annotations

import json
import os

from ._safety import SafetyError

MARKER_NAME = "workspace.json"


def marker_path(workspace: str) -> str:
    return os.path.join(os.path.dirname(os.path.realpath(workspace)), MARKER_NAME)


def read_marker(workspace: str) -> dict | None:
    """The marker for ``workspace`` or None if it is not a registered temporary copy."""
    ws = os.path.realpath(workspace)
    try:
        with open(marker_path(ws), encoding="utf-8") as handle:
            marker = json.load(handle)
    except (OSError, ValueError):
        return None
    if not isinstance(marker, dict) or marker.get("created_by") != "make_temp_copy":
        return None
    if os.path.realpath(str(marker.get("workspace", ""))) != ws:
        return None
    if os.path.realpath(str(marker.get("original_root", ""))) == ws:
        return None
    return marker


def require_temp_copy(workspace: str) -> dict:
    """Return the marker or raise SafetyError. Used before any write or test run."""
    if not os.path.isdir(workspace):
        raise SafetyError(f"workspace {workspace!r} is not a folder")
    marker = read_marker(workspace)
    if marker is None:
        raise SafetyError(
            f"{workspace!r} is not a temporary copy made by make_temp_copy; "
            "writes and test runs are only allowed in the temporary copy, never in the original folder")
    return marker
