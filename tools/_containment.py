"""Containment guardrails in code (canvas sections 9, 13, 16; AGENTS.md section 4 NEVER list).

One place for the checks that must not depend on a prompt:
  tools      check_tool_call      an agent may call only its own tools (the MCP server filters too)
  originals  check_write_target   a write or test run outside the registered temporary copy stops the run
  privacy    find_leaks, to_model nothing unmasked goes to the model, the report or the log
  never      forbidden_command    no commit, push, merge, deploy, install, remove, delete or network call
             check_endpoint       the only reachable host is the approved model endpoint
Events (a blocked tool call, for example) are recorded here and the orchestrator copies them into the
decision log after every handoff (drain_events).
"""
from __future__ import annotations

import os
import shlex
from urllib.parse import urlsplit

from ._mask import EMAIL, PHONE, Masker, secret_spans
from ._safety import SafetyError
from ._workspace import require_temp_copy

AGENT_TOOLS = {
    "auditor": ["list_files", "read_file", "run_security_rules"],
    "investigator": ["read_file", "read_code_structure"],
    "fixer-validator": ["apply_patch", "run_tests", "request_recheck"],
}
WRITING_TOOLS = ("apply_patch", "run_tests", "request_recheck")   # these take a ``workspace``


class ContainmentViolation(Exception):
    """A safety boundary was crossed. The orchestrator stops the run and raises an alert."""


class ToolNotAllowed(ValueError):
    """The agent asked for a tool it does not own. It gets an error; the run goes on."""


_events: list[tuple[str, str]] = []


def record(event: str, detail: str) -> None:
    _events.append((event, detail))


def drain_events() -> list[tuple[str, str]]:
    taken = list(_events)
    _events.clear()
    return taken


# ------------------------------------------------------------------ tools and originals
def agent_key(agent: str) -> str:
    return agent.replace("_", "-")


def check_tool_call(agent: str, tool: str, arguments: dict) -> None:
    """Raise ToolNotAllowed for a tool the agent does not own; ContainmentViolation for a write
    or test run whose workspace is not the registered temporary copy."""
    owned = AGENT_TOOLS.get(agent_key(agent))
    if owned is None or tool not in owned:
        record("tool_not_allowed", f"{agent} asked for {tool}; allowed: {', '.join(owned or [])}")
        raise ToolNotAllowed(f"tool {tool!r} is not available to the {agent} agent")
    if tool in WRITING_TOOLS:
        workspace = arguments.get("workspace", "")
        try:
            require_temp_copy(workspace)
        except SafetyError as exc:
            record("alert_write_outside_copy", f"{agent} called {tool} on {workspace!r}")
            raise ContainmentViolation(f"{tool} aimed outside the temporary copy: {exc}") from None


# ------------------------------------------------------------------ never
_GIT_READ_ONLY = {"status", "diff", "log", "show", "rev-parse", "ls-files", "--version"}
_INSTALLERS = {"pip", "pip3", "npm", "yarn", "pnpm", "apt", "apt-get", "brew", "choco", "winget", "conda",
               "poetry", "pipx", "uv", "gem", "cargo"}
_INSTALL_VERBS = {"install", "uninstall", "remove", "add", "upgrade", "update", "purge", "sync"}
_DELETERS = {"rm", "rmdir", "del", "erase", "rd", "unlink", "shred", "remove-item"}
_NETWORK = {"curl", "wget", "nc", "ncat", "ssh", "scp", "sftp", "ftp", "telnet", "invoke-webrequest", "iwr", "gh"}
_DEPLOY = {"kubectl", "terraform", "helm", "ansible-playbook", "heroku", "vercel", "flyctl", "serverless"}


def forbidden_command(command: str) -> str | None:
    """The reason a command line may not run, or None. Judged on the first word and, for Python,
    on ``-m pip``. A guard on the command text; the container at the pilot is the hard wall."""
    try:
        argv = shlex.split(command)
    except ValueError:
        return "the command cannot be read"
    if not argv:
        return None
    name = os.path.basename(argv[0]).lower().removesuffix(".exe")
    rest = [a.lower() for a in argv[1:]]
    if name == "git" and (not rest or rest[0] not in _GIT_READ_ONLY):
        return "git commit, push, merge and other changes are never allowed"
    if name in _INSTALLERS and rest and rest[0] in _INSTALL_VERBS:
        return "adding or removing packages is never allowed"
    if name in {"python", "python3", "py"} and "-m" in rest and rest[rest.index("-m") + 1:][:1] in (["pip"], ["ensurepip"]):
        return "adding or removing packages is never allowed"
    if name in _DELETERS:
        return "deleting files is never allowed"
    if name in _NETWORK:
        return "contacting a network host is never allowed"
    if name in _DEPLOY or (name == "docker" and rest[:1] in (["push"], ["login"])):
        return "deploying is never allowed"
    return None


def check_endpoint(url: str, approved: str) -> None:
    """Raise ContainmentViolation unless ``url`` is on the approved model endpoint (same scheme, host, port)."""
    if not approved or approved.lower() == "none":
        raise ContainmentViolation("no model endpoint is approved, so no network host may be contacted")
    want, got = urlsplit(approved), urlsplit(url)
    if (want.scheme, want.hostname, want.port) != (got.scheme, got.hostname, got.port):
        raise ContainmentViolation(f"{got.hostname or url!r} is not the approved model endpoint")


# ------------------------------------------------------------------ privacy
def find_leaks(data: object) -> list[str]:
    """Kinds (SECRET, EMAIL, PHONE) of any unmasked value anywhere inside ``data`` (strings, lists, dicts).
    Never returns the values themselves."""
    kinds: list[str] = []
    if isinstance(data, str):
        for line in data.splitlines() or [data]:
            if secret_spans(line):
                kinds.append("SECRET")
            if EMAIL.search(line):
                kinds.append("EMAIL")
            if PHONE.search(line):
                kinds.append("PHONE")
    elif isinstance(data, dict):
        for value in data.values():
            kinds += find_leaks(value)
    elif isinstance(data, (list, tuple)):
        for value in data:
            kinds += find_leaks(value)
    return sorted(set(kinds))


def to_model(text: str, masker: Masker) -> str:
    """The only way text may reach a model: masked, counted in ``masker.counts``, and checked again."""
    masked = masker.text(text)
    if find_leaks(masked):
        raise ContainmentViolation("a secret or personal value survived masking; nothing was sent to the model")
    return masked

