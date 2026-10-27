"""Offline stand-ins for the three agents. NO AI model: plain deterministic code.

Why they exist: no model endpoint is approved yet (AGENTS.md section 8), and real code must not
reach a model. Each stand-in does the job its prompt (agents/<name>.md) describes, reaches the code ONLY
through its own MCP server (`python tools/mcp_server.py --agent <name>`), and returns one JSON object that
holds only the state fields that agent owns. A model-backed runner replaces these functions later; the
orchestrator and the schemas do not change.

Honest limits of the stand-ins (a model is meant to do better):
  - Investigator: cannot tell a library function nobody calls (golden case_11, which needs a person)
    from a function whose callers live outside the project (case_01). Both look the same in the code, so
    it does not escalate on "no caller"; it only says so in traced_cause. It does hand over when an
    interpolated value is a SQL fragment, not a quoted value (case_07).
  - Fixer & Validator: writes a patch only for three one-line patterns: query = f"... '{value}' ..." followed by
    .execute(query) (SQLI, cases 01, 09, 10); subprocess.run(f"cmd {value}", shell=True) (CMDI, case 02); and
    path = os.path.join(base, name) (PATH, case 03). For anything else, such as a fix that spans files, it writes no patch.
"""
from __future__ import annotations

import os
import re

from . import AgentError
from .mcp_client import McpClient

SEVERITY_RANK = {"high": 0, "medium": 1, "low": 2}
RULE_CONFIDENCE = 0.90          # a rule matched; no model judged it (docs/roster.md)
PATH_RULES = ("SQLI", "CMDI", "PATH")
INJECTION = re.compile(
    r"ignore (?:all |your |any )?(?:previous )?(?:rules|instructions)|\bAI assistant\b|curl\s+\S+\s*\|\s*(?:sh|bash)",
    re.IGNORECASE)
PLACEHOLDER = re.compile(r"<(SECRET|EMAIL|PHONE)_\d+>")
FIX_APPROACH = {
    "SQLI": "Use a ? placeholder and pass the value as a parameter.",
    "CMDI": "Pass the command as a list with no shell.",
    "PATH": "Resolve the path and refuse it if it is outside the folder.",
}


def _call(client: McpClient, tool: str, arguments: dict) -> dict:
    reply = client.call(tool, arguments)
    if not reply["ok"]:
        raise AgentError(f"{tool} failed: {reply['error']['code']}: {reply['error']['message']}")
    return reply["result"]


def _is_test_file(path: str) -> bool:
    parts = path.split("/")
    return "tests" in parts[:-1] or parts[-1].startswith("test_")


def _norm(text: str) -> str:
    return PLACEHOLDER.sub(r"<\1>", text.strip())


# --------------------------------------------------------------------------- Auditor
def run_auditor(job: dict) -> dict:
    client = McpClient("auditor")
    try:
        if job["job"] == "audit":
            return _audit(client, job)
        if job["job"] == "recheck":
            return _recheck(client, job)
        raise AgentError(f"the auditor has no job {job['job']!r}")
    finally:
        client.close()


def _audit(client: McpClient, job: dict) -> dict:
    root, rules = job["source_folder"], job["rules"]["rules"]
    listing = _call(client, "list_files", {"root": root, "file_cap": job["policy"]["file_cap"]})
    scan = [f for f in listing["files"] if f.endswith(".py") or os.path.basename(f) == "requirements.txt"]
    result = {"matches": [], "skipped_rules": [], "sensitive_items_hidden": 0}
    if scan:
        result = _call(client, "run_security_rules", {"root": root, "rules_file": job["rules_file"], "files": scan})

    texts: dict[str, str] = {}
    hidden = 0  # counted from read_file only: it reads the whole file, so the rules count is a subset of it
    notes, kept, dropped = [], [], []
    for match in result["matches"]:
        if match["file"] not in texts:
            read = _call(client, "read_file", {"root": root, "path": match["file"]})
            texts[match["file"]] = read["content"]
            hidden += read.get("sensitive_items_hidden", 0)
            if INJECTION.search(read["content"]):
                notes.append({"event": "prompt_injection_attempt",
                              "detail": f"{match['file']}: text inside the file tries to give instructions; "
                                        "it was treated as data and ignored"})
        lines = texts[match["file"]].splitlines()
        if 1 <= match["line"] <= len(lines) and _norm(lines[match["line"] - 1]) == _norm(match["quoted_code"]):
            kept.append(match)
        else:
            dropped.append({"rule_id": match["rule_id"], "file": match["file"], "line": match["line"],
                            "reason": "the quoted code does not appear at that file and line"})

    severity = {r["id"]: r["severity"] for r in rules}
    position = {r["id"]: i for i, r in enumerate(rules)}
    kept.sort(key=lambda m: (SEVERITY_RANK[severity[m["rule_id"]]], position[m["rule_id"]], m["file"], m["line"]))
    candidates = [{
        "finding_id": f"F{n:03d}", "rule_id": m["rule_id"], "file": m["file"], "line": m["line"],
        "severity": severity[m["rule_id"]],
        "evidence": {"file": m["file"], "line": m["line"], "quoted_code": m["quoted_code"]},
        "confidence": RULE_CONFIDENCE, "detected_by": "rule", "rank": n,
    } for n, m in enumerate(kept, 1)]
    return {
        "file_list": {"files": listing["files"], "skipped_dirs": listing["skipped_dirs"],
                      "truncated": listing["truncated"]},
        "skipped_files": result.get("skipped_files", []),
        "skipped_rules": result["skipped_rules"],
        "candidate_findings": candidates,
        "dropped_findings": dropped,
        "notes": notes,
        "usage": {"ai_calls": 0, "tokens_in": 0, "tokens_out": 0, "sensitive_items_hidden": hidden},
    }


def _recheck(client: McpClient, job: dict) -> dict:
    result = _call(client, "run_security_rules",
                   {"root": job["workspace"], "rules_file": job["rules_file"], "files": job["files"]})
    clear = not result["matches"] and not result["skipped_rules"] and not result.get("skipped_files")
    return {"recheck_results": [{"finding_id": job["finding_id"], "attempt": job["attempt"], "clear": clear,
                                 "matches": result["matches"]}],
            "usage": {"ai_calls": 0, "tokens_in": 0, "tokens_out": 0,
                      "sensitive_items_hidden": result.get("sensitive_items_hidden", 0)}}


# --------------------------------------------------------------------------- Investigator
def run_investigator(job: dict) -> dict:
    client = McpClient("investigator")
    try:
        return _investigate(client, job)
    finally:
        client.close()


def _investigate(client: McpClient, job: dict) -> dict:
    finding, root = job["finding"], job["source_folder"]
    fid, rule, file = finding["finding_id"], finding["rule_id"], finding["file"]
    usage = {"ai_calls": 0, "tokens_in": 0, "tokens_out": 0, "sensitive_items_hidden": 0}

    def entry(traced, approach, fixable, reason):
        return {"investigations": [{"finding_id": fid, "traced_cause": traced, "fix_approach": approach,
                                    "fixable": fixable, "handoff_reason": reason}], "usage": usage}

    if rule not in PATH_RULES:
        return entry({"explanation": f"{rule}: the weak value is written in the source itself, so there is "
                                     "no input path to trace.", "path": [file]},
                     "No automatic fix: the rule setting leaves this to a person.", True, None)

    read = _call(client, "read_file", {"root": root, "path": file})
    usage["sensitive_items_hidden"] += read.get("sensitive_items_hidden", 0)
    lines = read["content"].splitlines()
    flagged = lines[finding["line"] - 1] if 1 <= finding["line"] <= len(lines) else ""

    # A fragment of SQL (not a quoted value) is interpolated: a placeholder cannot replace it.
    opening = re.search(r"\bf([\"'])", flagged)
    inner = "'" if opening is None or opening.group(1) == '"' else '"'     # a quoted value sits in the other quote
    if rule == "SQLI" and re.search(rf"(?<!{inner})\{{\w+\}}(?!{inner})", flagged):
        return entry({"explanation": "A caller-supplied piece of SQL is put into the query as text, not a value.",
                      "path": [file]}, None, False,
                     "needs a redesign: the caller supplies part of the SQL itself, so a placeholder cannot "
                     "replace it; clients would have to send structured filters")

    sources = [f for f in job["file_list"]["files"] if f.endswith(".py") and not _is_test_file(f)]
    structure = _call(client, "read_code_structure", {"root": root, "files": sources})
    functions = structure["functions"]
    here = next((f for f in functions if f["file"] == file and f["start_line"] <= finding["line"] <= f["end_line"]),
                None)
    if here is None:
        return entry(None, None, False, "cause unclear: the weak spot is not inside a function I can trace")

    path_files, current, seen = [file], here, {(here["file"], here["name"])}
    while current.get("callers"):
        caller = current["callers"][0]
        nxt = next((f for f in functions if (f["file"], f["name"]) == (caller["file"], caller["function"])), None)
        if nxt is None or (nxt["file"], nxt["name"]) in seen:
            break
        seen.add((nxt["file"], nxt["name"]))
        if nxt["file"] not in path_files:
            path_files.insert(0, nxt["file"])
        current = nxt
    for call in here["calls"]:
        callee = next((f for f in functions if f["name"] == call["name"] and f["file"] != file), None)
        if callee and callee["file"] not in path_files:
            path_files.append(callee["file"])

    callers = here.get("callers", [])
    explanation = (f"{here['name']} is called from {callers[0]['function']} in {callers[0]['file']}."
                   if callers else f"No caller of {here['name']} was found in the project; where its input "
                                   "comes from is not visible here.")
    return entry({"explanation": explanation, "path": path_files}, FIX_APPROACH[rule], True, None)


# --------------------------------------------------------------------------- Fixer & Validator
def run_fixer_validator(job: dict) -> dict:
    client = McpClient("fixer-validator")
    try:
        if job["job"] == "baseline_tests":
            ran = _call(client, "run_tests", {"workspace": job["workspace"], "test_command": job["test_command"],
                                              "timeout_seconds": job["test_timeout_seconds"]})
            return {"baseline_tests": {"outcome": ran["outcome"], "exit_code": ran["exit_code"]},
                    "usage": {"ai_calls": 0, "tokens_in": 0, "tokens_out": 0, "sensitive_items_hidden": 0}}
        if job["job"] == "fix":
            return _fix(client, job)
        raise AgentError(f"the fixer-validator has no job {job['job']!r}")
    finally:
        client.close()


def _sqli_patch(file: str, text: str, line_no: int) -> str | None:
    """A unified diff for  query = f"... '{value}' ..."  +  .execute(query), or None."""
    lines = text.splitlines()
    if not 1 <= line_no <= len(lines):
        return None
    flagged = lines[line_no - 1]
    m = re.match(r"^(\s*)(\w+)\s*=\s*f([\"'])(.*)\3\s*$", flagged)
    if not m:
        return None
    indent, var, quote, body = m.groups()
    params = re.findall(r"'\{(\w+)\}'", body)
    rest = re.sub(r"'\{\w+\}'", "?", body)
    if not params or "{" in rest:
        return None
    for k in range(line_no, min(len(lines), line_no + 10)):
        found = re.search(rf"\.execute\(\s*{re.escape(var)}\s*\)", lines[k])
        if found:
            break
    else:
        return None
    values = f"({params[0]},)" if len(params) == 1 else "(" + ", ".join(params) + ")"
    new_query = f"{indent}{var} = {quote}{rest}{quote}"
    new_exec = lines[k][:found.start()] + f".execute({var}, {values})" + lines[k][found.end():]
    first = line_no - 1 if line_no > 1 else line_no
    body_lines = [" " + lines[i] for i in range(first - 1, line_no - 1)]
    if k == line_no:                                  # adjacent lines: one block, removals first (a normal diff)
        body_lines += ["-" + flagged, "-" + lines[k], "+" + new_query, "+" + new_exec]
    else:
        body_lines += ["-" + flagged, "+" + new_query]
        body_lines += [" " + lines[i] for i in range(line_no, k)]
        body_lines += ["-" + lines[k], "+" + new_exec]
    old_len = sum(1 for b in body_lines if b[0] in " -")
    new_len = sum(1 for b in body_lines if b[0] in " +")
    return "\n".join([f"--- a/{file}", f"+++ b/{file}", f"@@ -{first},{old_len} +{first},{new_len} @@"] + body_lines) + "\n"


def _line_diff(file: str, lines: list[str], line_no: int, replacement: list[str]) -> str:
    """A unified diff that replaces line ``line_no`` (1-based) with ``replacement``, with one line of context on each side."""
    before = lines[line_no - 2:line_no - 1]
    after = lines[line_no:line_no + 1]
    start = line_no - len(before)
    body = [" " + t for t in before] + ["-" + lines[line_no - 1]] + ["+" + t for t in replacement] + [" " + t for t in after]
    old_len = len(before) + 1 + len(after)
    new_len = len(before) + len(replacement) + len(after)
    return "\n".join([f"--- a/{file}", f"+++ b/{file}", f"@@ -{start},{old_len} +{start},{new_len} @@"] + body) + "\n"


_SHELL_CALL = re.compile(r"^(?P<pre>.*?\bsubprocess\.(?:run|call|check_output|check_call|Popen)\()\s*f(?P<q>[\"'])(?P<body>.*?)(?P=q)\s*,\s*shell\s*=\s*True(?P<rest>.*)$")
_SHELL_META = re.compile(r"[|&;<>$`*?(){}\[\]\\\"']")


def _cmdi_patch(file: str, text: str, line_no: int) -> str | None:
    """subprocess.run(f"echo checking {host}", shell=True, ...)  becomes  subprocess.run(["echo", "checking", host], ...) with no shell.
    Only when every word of the command is plain text or exactly one {name}; anything with shell syntax gets no patch."""
    lines = text.splitlines()
    if not 1 <= line_no <= len(lines):
        return None
    m = _SHELL_CALL.match(lines[line_no - 1])
    if not m:
        return None
    words = []
    for token in m.group("body").split():
        name = re.fullmatch(r"\{([A-Za-z_]\w*)\}", token)
        if name:
            words.append(name.group(1))
        elif _SHELL_META.search(token):
            return None
        else:
            words.append(f"{m.group('q')}{token}{m.group('q')}")
    if not words:
        return None
    return _line_diff(file, lines, line_no, [m.group("pre") + "[" + ", ".join(words) + "]" + m.group("rest")])


_PATH_JOIN_LINE = re.compile(r"^(?P<indent>\s*)(?P<var>\w+)\s*=\s*os\.path\.join\(\s*(?P<base>[\w.]+)\s*,\s*(?P<name>[\w.]+)\s*\)\s*$")


def _path_patch(file: str, text: str, line_no: int) -> str | None:
    """path = os.path.join(base, name)  becomes a resolved path that must stay inside base, or a ValueError."""
    lines = text.splitlines()
    if not 1 <= line_no <= len(lines):
        return None
    m = _PATH_JOIN_LINE.match(lines[line_no - 1])
    if not m:
        return None
    i, var, base, name = m.group("indent"), m.group("var"), m.group("base"), m.group("name")
    return _line_diff(file, lines, line_no, [
        f"{i}{var} = os.path.realpath(os.path.join({base}, {name}))",
        f"{i}if os.path.commonpath([os.path.realpath({base}), {var}]) != os.path.realpath({base}):",
        f"{i}    raise ValueError(\"the path is outside the allowed folder\")"])


def _fix(client: McpClient, job: dict) -> dict:
    finding, fid, attempt = job["finding"], job["finding"]["finding_id"], job["attempt"]
    before = job["baseline"]
    usage = {"ai_calls": 0, "tokens_in": 0, "tokens_out": 0, "sensitive_items_hidden": 0}

    def attempt_entry(diff, changed, after, recheck, decision, risk):
        return {"fix_attempts": [{"finding_id": fid, "attempt": attempt, "patch_diff": diff,
                                  "files_changed": changed, "tests": {"before": before, "after": after},
                                  "recheck": recheck, "decision": decision, "residual_risk": risk}],
                "usage": usage}

    writer = {"SQLI": _sqli_patch, "CMDI": _cmdi_patch, "PATH": _path_patch}.get(finding["rule_id"])
    diff = writer(finding["file"], job["source"], finding["line"]) if writer else None
    if diff is None:
        return attempt_entry(None, [], None, "not_run", "reject",
                             "No patch was written, so nothing was changed and the weak spot is still there.")
    again = "retry" if attempt == 1 else "reject"
    applied = client.call("apply_patch", {"workspace": job["workspace"], "patch_diff": diff})
    if not applied["ok"]:
        return attempt_entry(diff, [], None, "not_run", again,
                             "The patch did not apply or broke the syntax and was undone: "
                             + applied["error"]["message"][:120])
    changed = applied["result"]["files_changed"]
    ran = _call(client, "run_tests", {"workspace": job["workspace"], "test_command": job["test_command"],
                                      "timeout_seconds": job["test_timeout_seconds"]})
    if ran["outcome"] != "pass":
        return attempt_entry(diff, changed, ran["outcome"], "not_run", again,
                             "The project's tests did not pass after the change.")
    recheck = client.call("request_recheck", {"workspace": job["workspace"], "files": changed})
    if not recheck["ok"]:
        return attempt_entry(diff, changed, "pass", "not_run", again,
                             "The re-check could not run: " + recheck["error"]["message"][:120])
    if not recheck["result"]["clear"]:
        return attempt_entry(diff, changed, "pass", "not_clear", again, "A rule still matches the changed files.")
    return attempt_entry(diff, changed, "pass", "clear", "keep",
                         "Only the project's own tests were run; they may not cover every input to this code.")
