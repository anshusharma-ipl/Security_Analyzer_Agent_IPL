"""Minimal MCP server (JSON-RPC 2.0 over stdio, standard library only) for the seven agent tools.

    python -m tools.mcp_server --agent auditor | investigator | fixer-validator
    python -m tools.mcp_server --check

Each agent sees and may call only its own tools (AGENTS.md section 4). The tool functions are
called unchanged: every safety rule still lives in tools/, none is added or moved here.
Nothing else is exposed: no shell, no general file write, and no orchestrator helper.

Messages are one JSON object per line. Supported: initialize, notifications/initialized,
tools/list, tools/call. Protocol faults (bad JSON, unknown method, unknown or not-owned tool)
are JSON-RPC errors; a tool that fails, or arguments that break the schema, come back as an
MCP result with isError true. A traceback is never sent.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if __package__ in (None, ""):  # started as a script: python tools/mcp_server.py --agent <name>
    sys.path.insert(0, ROOT)
    __package__ = "tools"
    importlib.import_module("tools")  # makes the relative imports below resolve

from ._safety import SafetyError
from ._schema import SchemaError, validate_args
from .cli import TOOLS

AGENT_TOOLS = {
    "auditor": ["list_files", "read_file", "run_security_rules"],
    "investigator": ["read_file", "read_code_structure"],
    "fixer-validator": ["apply_patch", "run_tests", "request_recheck"],
}

DESCRIPTIONS = {
    "list_files": "List the project's files (read only, capped by file_cap).",
    "read_file": "Read one project file with sensitive values hidden (read only).",
    "run_security_rules": "Run the text-pattern security rules from the rules file on the given files (read only).",
    "read_code_structure": "Show the functions, classes and calls of the given Python files (read only).",
    "apply_patch": "Apply a unified diff to the temporary copy only; undone if the code stops being valid.",
    "run_tests": "Run the test command inside the temporary copy only, with a time limit.",
    "request_recheck": "Re-run the security rules on the temporary copy to see whether a finding is gone.",
}

SUPPORTED_VERSIONS = ["2025-06-18", "2025-03-26", "2024-11-05"]
PARSE_ERROR, INVALID_REQUEST, METHOD_NOT_FOUND, INVALID_PARAMS = -32700, -32600, -32601, -32602
_SCHEMA_DIR = os.path.join(ROOT, "schemas")


def input_schema(tool_name: str) -> dict:
    """The tool's arguments schema from schemas/, with its $defs so every $ref resolves."""
    with open(os.path.join(_SCHEMA_DIR, f"tool_{tool_name}.schema.json"), encoding="utf-8") as handle:
        schema = json.load(handle)
    return {"$schema": schema["$schema"], "$defs": schema.get("$defs", {}), **schema["properties"]["arguments"]}


def _reply(request_id, result=None, error=None) -> dict:
    message = {"jsonrpc": "2.0", "id": request_id}
    if error is not None:
        message["error"] = error
    else:
        message["result"] = result
    return message


def _error(request_id, code: int, text: str) -> dict:
    return _reply(request_id, error={"code": code, "message": text})


def _tool_result(text: str, is_error: bool) -> dict:
    return {"content": [{"type": "text", "text": text}], "isError": is_error}


def _call_tool(agent: str, params: dict) -> dict:
    """Run one tool. Raises KeyError(message) for a tool this agent may not call."""
    name = params.get("name")
    if name not in AGENT_TOOLS[agent]:
        raise KeyError(f"tool {name!r} is not available to the {agent} agent; allowed: {', '.join(AGENT_TOOLS[agent])}")
    arguments = params.get("arguments", {})
    try:
        validate_args(name, arguments)
        envelope = TOOLS[name](**arguments)
    except SchemaError as exc:
        return _tool_result(f"arguments do not match the schema for {name}: {exc}", True)
    except SafetyError as exc:
        return _tool_result(f"refused by a safety rule: {exc}", True)
    except Exception as exc:  # never leak a traceback; the type name is enough to report
        return _tool_result(f"{name} failed unexpectedly ({type(exc).__name__})", True)
    return _tool_result(json.dumps(envelope["response"], ensure_ascii=False), not envelope["response"]["ok"])


def handle(message: object, agent: str) -> dict | None:
    """Turn one decoded JSON-RPC message into a response (None for a notification)."""
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0" or not isinstance(message.get("method"), str):
        return _error(message.get("id") if isinstance(message, dict) else None, INVALID_REQUEST,
                      "not a JSON-RPC 2.0 request")
    method, request_id = message["method"], message.get("id")
    if "id" not in message:
        return None  # a notification (for example notifications/initialized) gets no reply
    params = message.get("params", {})
    if not isinstance(params, dict):
        return _error(request_id, INVALID_PARAMS, "params must be an object")

    if method == "initialize":
        requested = params.get("protocolVersion")
        version = requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0]
        return _reply(request_id, {
            "protocolVersion": version,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": f"security-analyzer-{agent}", "version": "1.0.0"},
        })
    if method == "tools/list":
        return _reply(request_id, {"tools": [
            {"name": n, "description": DESCRIPTIONS[n], "inputSchema": input_schema(n)} for n in AGENT_TOOLS[agent]]})
    if method == "tools/call":
        if not isinstance(params.get("name"), str):
            return _error(request_id, INVALID_PARAMS, "params.name must be a tool name")
        if not isinstance(params.get("arguments", {}), dict):
            return _error(request_id, INVALID_PARAMS, "params.arguments must be an object")
        try:
            return _reply(request_id, _call_tool(agent, params))
        except KeyError as exc:
            return _error(request_id, INVALID_PARAMS, exc.args[0])
    return _error(request_id, METHOD_NOT_FOUND, f"method {method!r} is not supported")


def serve(agent: str, stdin, stdout) -> None:
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            response = _error(None, PARSE_ERROR, "the message is not valid JSON")
        else:
            response = handle(message, agent)
        if response is not None:
            stdout.write(json.dumps(response) + "\n")
            stdout.flush()


# ---------------------------------------------------------------- --check

class _Client:
    """Talks to one server process, one request at a time."""

    def __init__(self, agent: str) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(ROOT, "tools", "mcp_server.py"), "--agent", agent], cwd=ROOT, text=True, encoding="utf-8",
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        self.next_id = 0

    def request(self, method: str, params: dict | None = None) -> dict:
        self.next_id += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.next_id, "method": method,
                                          "params": params or {}}) + "\n")
        self.proc.stdin.flush()
        return json.loads(self.proc.stdout.readline())

    def close(self) -> None:
        self.proc.stdin.close()
        self.proc.wait(timeout=10)
        self.proc.stdout.close()
        self.proc.stderr.close()


def check() -> int:
    from .orchestrator_helpers import make_temp_copy

    case = os.path.join(ROOT, "golden", "case_01_sqli_fstring")
    rules = os.path.join(ROOT, "golden", "rules.json")
    copy_info = make_temp_copy(case, rules)
    calls = {
        "auditor": ("run_security_rules", {"root": case, "rules_file": rules, "files": ["src/users.py"]}),
        "investigator": ("read_code_structure", {"root": case, "files": ["src/users.py"]}),
        "fixer-validator": ("request_recheck", {"workspace": copy_info["workspace"], "files": ["src/users.py"]}),
    }
    failures = 0
    try:
        for agent, owned in AGENT_TOOLS.items():
            client = _Client(agent)
            try:
                client.request("initialize", {"protocolVersion": SUPPORTED_VERSIONS[0]})
                listed = [t["name"] for t in client.request("tools/list")["result"]["tools"]]
                name, arguments = calls[agent]
                answer = client.request("tools/call", {"name": name, "arguments": arguments})
                called = "result" in answer and not answer["result"]["isError"]
                other = next(t for t in TOOLS if t not in owned)
                refused = "error" in client.request("tools/call", {"name": other, "arguments": {}})
            finally:
                client.close()
            results = [("lists only its tools", listed == owned), (f"calls {name}", called),
                       (f"refuses {other}", refused)]
            for label, passed in results:
                failures += not passed
                print(f"{agent:16} {'ok  ' if passed else 'FAIL'} {label}")
    finally:
        import shutil
        shutil.rmtree(copy_info["run_dir"], ignore_errors=True)
    print("check passed" if not failures else f"check FAILED ({failures})")
    return 1 if failures else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MCP server for the Security Analyzer Agent tools")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--agent", choices=sorted(AGENT_TOOLS), help="serve only this agent's tools")
    group.add_argument("--check", action="store_true", help="start each agent's server and test it")
    args = parser.parse_args(argv)
    if args.check:
        return check()
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    serve(args.agent, sys.stdin, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
