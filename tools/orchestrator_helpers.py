"""Orchestrator helpers. These are NOT agent tools: the agents cannot choose or skip them.

make_temp_copy   copy the project to a fresh folder that fixes and tests may touch
hash_originals   fingerprint every original file before the run
verify_originals compare the originals to that fingerprint at the end of the run

Folder layout made by make_temp_copy:
    <run_dir>/copy/            the temporary copy (the only place anything is written)
    <run_dir>/workspace.json   marker that registers the copy (outside the copy on purpose)
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile

from ._safety import SKIP_DIRS, SafetyError, is_inside, is_link
from ._workspace import MARKER_NAME


def _walk(root: str):
    """Yield (relative path, absolute path) of every file below root, depth first, sorted.
    Skips SKIP_DIRS and never follows a link."""
    root_real = os.path.realpath(root)
    pending = [root_real]
    while pending:
        current = pending.pop()
        with os.scandir(current) as it:
            entries = sorted(it, key=lambda e: e.name)
        subfolders = []
        for entry in entries:
            rel = os.path.relpath(entry.path, root_real).replace(os.sep, "/")
            if is_link(entry.path):
                yield rel, entry.path
            elif entry.is_dir(follow_symlinks=False):
                if entry.name not in SKIP_DIRS:
                    subfolders.append(entry.path)
            elif entry.is_file(follow_symlinks=False):
                yield rel, entry.path
        pending.extend(reversed(subfolders))


def make_temp_copy(original_root: str, rules_file: str | None = None, run_dir: str | None = None) -> dict:
    """Copy ``original_root`` into <run_dir>/copy and register it. Returns the paths.

    Links are never copied (a copied link could point back into the original and let a write
    escape). Folders in SKIP_DIRS are not copied. ``rules_file`` is remembered so
    request_recheck can find the rules. Raises SafetyError if the run folder is inside the
    project (the copy would copy itself).
    """
    original = os.path.realpath(original_root)
    if not os.path.isdir(original):
        raise SafetyError(f"project folder {original_root!r} does not exist")
    run_dir = os.path.realpath(run_dir) if run_dir else os.path.realpath(tempfile.mkdtemp(prefix="saa-run-"))
    if is_inside(original, run_dir):
        raise SafetyError(f"run folder {run_dir!r} is inside the project folder; choose a folder outside it")
    if is_inside(run_dir, original):
        raise SafetyError("the project folder is inside the run folder")
    copy = os.path.join(run_dir, "copy")
    if os.path.exists(copy):
        raise SafetyError(f"{copy!r} already exists; every run needs a fresh folder")
    os.makedirs(copy)

    skipped_links: list[str] = []
    for rel, src in _walk(original):
        if is_link(src):
            skipped_links.append(rel)
            continue
        dest = os.path.join(copy, *rel.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copyfile(src, dest)
        shutil.copystat(src, dest)

    marker = {"created_by": "make_temp_copy", "workspace": copy, "original_root": original,
              "rules_file": os.path.realpath(rules_file) if rules_file else None}
    with open(os.path.join(run_dir, MARKER_NAME), "w", encoding="utf-8") as handle:
        json.dump(marker, handle, indent=2)
    return {"workspace": copy, "run_dir": run_dir, "original_root": original, "skipped_links": sorted(skipped_links)}


def _fingerprint(path: str) -> str:
    if is_link(path):
        try:
            return "link:" + os.readlink(path)
        except OSError:
            return "link:unreadable"
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def hash_originals(original_root: str) -> dict[str, str]:
    """Map every original file (relative path) to a SHA-256. .git, node_modules, .venv and
    __pycache__ are not hashed: they are not copied either, and git rewrites its index when
    anyone runs ``git status``, which would raise a false alarm."""
    if not os.path.isdir(original_root):
        raise SafetyError(f"project folder {original_root!r} does not exist")
    return {rel: _fingerprint(path) for rel, path in _walk(original_root)}


def verify_originals(original_root: str, baseline: dict[str, str]) -> dict:
    """Compare the originals to ``baseline`` (from hash_originals). ``unchanged`` is True
    only when no file was changed, added or removed. A True here is what lets the run end."""
    now = hash_originals(original_root)
    changed = sorted(p for p in baseline if p in now and now[p] != baseline[p])
    removed = sorted(p for p in baseline if p not in now)
    added = sorted(p for p in now if p not in baseline)
    return {"unchanged": not (changed or removed or added), "changed": changed, "added": added, "removed": removed}
