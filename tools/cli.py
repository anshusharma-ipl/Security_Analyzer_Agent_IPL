"""Command-line wrapper:  python -m tools.cli <tool_name> '<json args>'

Prints the tool's result envelope ({tool, arguments, response}) as JSON on stdout.
Exit code: 0 the tool ran and succeeded, 1 the tool ran and returned an error envelope,
2 the call itself was wrong (unknown tool, bad JSON, arguments that fail the schema).
The orchestrator helpers (make_temp_copy, hash_originals, verify_originals) are
deliberately NOT available here: the agents cannot choose or skip them.
"""
from __future__ import annotations

import json
import sys

from ._schema import SchemaError
from ._safety import SafetyError
from .apply_patch import apply_patch
from .list_files import list_files
from .read_code_structure import read_code_structure
from .read_file import read_file
from .request_recheck import request_recheck
from .run_security_rules import run_security_rules
from .run_tests import run_tests

TOOLS = {
    "list_files": list_files,
    "read_file": read_file,
    "run_security_rules": run_security_rules,
    "read_code_structure": read_code_structure,
    "apply_patch": apply_patch,
    "run_tests": run_tests,
    "request_recheck": request_recheck,
}

USAGE = "usage: python -m tools.cli <tool_name> '<json args>'\ntools: " + ", ".join(TOOLS)


def call(tool_name: str, arguments: dict) -> dict:
    """Run one tool by name. Raises KeyError for an unknown tool, SchemaError for bad arguments."""
    return TOOLS[tool_name](**arguments)


def _usage_error(message: str) -> int:
    print(json.dumps({"ok": False, "error": {"code": "bad_call", "message": message}}, indent=2))
    print(USAGE, file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        return _usage_error("expected exactly two arguments: a tool name and a JSON object")
    name, raw = argv
    if name not in TOOLS:
        return _usage_error(f"unknown tool {name!r}")
    try:
        arguments = json.loads(raw)
    except ValueError as exc:
        return _usage_error(f"the arguments are not valid JSON: {exc}")
    if not isinstance(arguments, dict):
        return _usage_error("the arguments must be a JSON object")
    try:
        envelope = call(name, arguments)
    except SchemaError as exc:
        return _usage_error(f"arguments do not match the schema: {exc}")
    except TypeError as exc:
        return _usage_error(f"wrong argument names for {name}: {exc}")
    except SafetyError as exc:
        return _usage_error(str(exc))
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(envelope, indent=2, ensure_ascii=False))
    return 0 if envelope["response"]["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
