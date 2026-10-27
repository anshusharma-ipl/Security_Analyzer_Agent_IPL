"""Tiny MCP client. An agent gets its tools ONLY through this: it starts
`python tools/mcp_server.py --agent <name>` and talks JSON-RPC 2.0 over stdio."""
from __future__ import annotations

import json
import os
import subprocess
import sys

from tools import _containment

from . import progress

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVER = os.path.join(ROOT, "tools", "mcp_server.py")


def _report_outcome(name: str, reply: dict, agent: str) -> None:
    """The two results a person wants to see as they happen: did the tests pass, is the re-check clear."""
    result = reply.get("result") if reply.get("ok") else None
    if name == "run_tests" and result:
        progress.emit("tool", f"Tests: {result.get('outcome')}", agent=agent, tool=name, outcome=result.get("outcome"))
    elif name == "request_recheck" and result:
        progress.emit("tool", "Re-check: clear" if result.get("clear") else "Re-check: the rule still matches",
                      agent=agent, tool=name, outcome="clear" if result.get("clear") else "not_clear")


class McpError(RuntimeError):
    """A protocol fault: the server refused the call (for example a tool the agent does not own)."""


class McpClient:
    def __init__(self, agent: str) -> None:
        self.agent = agent
        self._next_id = 0
        self._proc = subprocess.Popen(
            [sys.executable, SERVER, "--agent", agent], cwd=ROOT, text=True, encoding="utf-8",
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self._request("initialize", {"protocolVersion": "2025-06-18"})
        self._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.tool_defs = self._request("tools/list")["tools"]      # name, description, inputSchema (for a model)
        self.tools = [t["name"] for t in self.tool_defs]

    def _send(self, message: dict) -> None:
        self._proc.stdin.write(json.dumps(message) + "\n")
        self._proc.stdin.flush()

    def _request(self, method: str, params: dict | None = None) -> dict:
        self._next_id += 1
        self._send({"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": params or {}})
        line = self._proc.stdout.readline()
        if not line:
            raise McpError("the MCP server closed unexpectedly")
        reply = json.loads(line)
        if "error" in reply:
            raise McpError(reply["error"]["message"])
        return reply["result"]

    def call(self, name: str, arguments: dict) -> dict:
        """Call one tool. Returns {ok, result} or {ok: False, error}. A refusal by the schema or a
        safety rule (plain text from the server) comes back as error code 'refused'. A tool the agent does not
        own comes back as error code 'tool_not_allowed'; a write aimed outside the temporary copy raises
        ContainmentViolation, which the orchestrator turns into a stopped run."""
        try:
            _containment.check_tool_call(self.agent, name, arguments)
        except _containment.ToolNotAllowed as exc:
            return {"ok": False, "error": {"code": "tool_not_allowed", "message": str(exc)}}
        progress.emit("tool", progress.describe_tool(name, arguments), agent=self.agent, tool=name)
        result = self._request("tools/call", {"name": name, "arguments": arguments})
        text = result["content"][0]["text"]
        try:
            parsed = json.loads(text)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict) and "ok" in parsed:
            _report_outcome(name, parsed, self.agent)
            return parsed
        return {"ok": False, "error": {"code": "refused", "message": text}}

    def close(self) -> None:
        try:
            self._proc.stdin.close()
            self._proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            self._proc.kill()
        self._proc.stdout.close()
