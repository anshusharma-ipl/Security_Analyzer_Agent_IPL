"""Path-safety helpers used by every tool and by the orchestrator helpers.

Rules (AGENTS.md section 4, canvas section 13):
  - every path is resolved with os.path.realpath before it is used;
  - a symlink or NTFS junction that leaves the project is refused;
  - nothing is ever written to the original folder.
"""
from __future__ import annotations

import os

SKIP_DIRS = frozenset({".git", "node_modules", ".venv", "__pycache__"})


class SafetyError(ValueError):
    """A path or folder violates a safety rule. The message says which and why."""


_LINK_TAGS = (0xA000000C, 0xA0000003)  # Windows reparse tags: symlink, junction (mount point)


def is_link(path: str) -> bool:
    """True for a symlink or an NTFS junction (os.path.islink misses junctions on 3.11).

    Other reparse points (for example OneDrive placeholders) are not links."""
    if os.path.islink(path):
        return True
    try:
        return getattr(os.lstat(path), "st_reparse_tag", 0) in _LINK_TAGS
    except OSError:
        return False


def is_inside(root: str, path: str) -> bool:
    """True when realpath(path) is root itself or below it."""
    root_real, path_real = os.path.realpath(root), os.path.realpath(path)
    return path_real == root_real or path_real.startswith(root_real + os.sep)


def resolve_inside(root: str, rel: str) -> str:
    """Return the real absolute path of ``rel`` under ``root``, or raise SafetyError.

    Refuses absolute paths, ``..`` escapes, and any component that is a symlink or
    junction whose target is outside the root.
    """
    root_real = os.path.realpath(root)
    if not os.path.isdir(root_real):
        raise SafetyError(f"root {root!r} is not a folder")
    if os.path.isabs(rel) or rel.startswith(("/", "\\")) or (len(rel) > 1 and rel[1] == ":"):
        raise SafetyError(f"path {rel!r} is absolute; only paths inside the project are allowed")
    current = root_real
    for part in rel.replace("\\", "/").split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            raise SafetyError(f"path {rel!r} climbs out of the project with '..'")
        current = os.path.join(current, part)
        if is_link(current) and not is_inside(root_real, current):
            raise SafetyError(f"{part!r} in {rel!r} is a link that leaves the project")
    resolved = os.path.realpath(current)
    if not is_inside(root_real, resolved):
        raise SafetyError(f"path {rel!r} resolves outside the project")
    return resolved
