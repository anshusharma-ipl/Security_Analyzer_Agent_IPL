"""Live progress: the running scan reports what it is doing, and the console shows it as a list of steps.

A scan runs in one thread. The console sets a sink for that thread (set_sink); the orchestrator, the agents' tool client and the
model client call emit() as they work. With no sink set (tests, the command line) emit() does nothing, so nothing else changes.

What is reported is only names and short labels (an agent, a tool, a file name, a count). Never file contents, a patch or a
tool result, so the live view cannot leak anything the masking already removed from the model's input.
"""
from __future__ import annotations

import threading
import time

_local = threading.local()


def set_sink(sink) -> None:
    """``sink(step: dict)`` is called for every step of the scan running in THIS thread."""
    _local.sink = sink


def clear_sink() -> None:
    _local.sink = None


def describe_tool(name: str, args: dict) -> str:
    files = args.get("files")
    count = len(files) if isinstance(files, list) else 0
    return {
        "list_files": "Listing the project's files",
        "read_file": f"Reading {str(args.get('path', 'a file'))[:80]}",
        "run_security_rules": f"Running the security rules on {count} file{'s' if count != 1 else ''}",
        "read_code_structure": "Reading how the code is built (functions and callers)",
        "apply_patch": "Applying the patch in the temporary copy",
        "run_tests": "Running the project's own tests in the copy",
        "request_recheck": "Re-checking the changed files with the security rules",
    }.get(name, f"Using {name}")


def emit(kind: str, text: str, **extra) -> None:
    """kind: agent (a handoff starts or ends), tool (a tool call), model (a model request), note (anything else)."""
    sink = getattr(_local, "sink", None)
    if sink is None:
        return
    try:
        sink({"t": round(time.time(), 3), "kind": kind, "text": text[:200], **extra})
    except Exception:  # noqa: BLE001 - a display problem must never stop a scan
        pass
