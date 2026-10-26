"""Workflow orchestrator. PLAIN CODE, NOT AN AGENT (canvas section 9, AGENTS.md section 3).

Fixed steps, in this order. Agents cannot choose, skip or reorder them:
  1. validate rules.json
  2. make the temporary copy (and fingerprint the originals first)
  3. run the Auditor
  4. for each ranked finding: run the Investigator, then the Fixer & Validator
  5. write the proposal to review_queue.json and WAIT for a person to approve / edit / reject
  6. run verify_originals
  7. write the decision log and the report

Every handoff goes through here; agents never call each other. Before every handoff the whole state is
validated against schemas/state.schema.json; an agent's output is accepted only if it writes just the
fields it owns and the merged state is still valid. The orchestrator alone sets each finding's status,
the totals, the approvals and the audit log. Nothing is ever applied to the original folder: approved
fixes are written to out/<run_id>/fixes.patch for a person to apply.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import shutil
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import validate  # noqa: E402  (schema checks and the code checks a schema cannot state)
from agents import AgentError, offline_agents  # noqa: E402
from tools.apply_patch import apply_patch  # noqa: E402
from tools.orchestrator_helpers import hash_originals, make_temp_copy, verify_originals  # noqa: E402
from tools.read_file import read_file  # noqa: E402
from tools.request_recheck import request_recheck  # noqa: E402
from tools.run_tests import run_tests  # noqa: E402

DEFAULT_POLICY = {
    "file_cap": 200, "max_retries": 1, "test_command": "python -m unittest discover -s tests",
    "ai_call_cap": 60, "time_cap_seconds": 1200, "confidence_gate": 0.7,
    "step_cap": 50, "token_cap_input": 400000, "token_cap_output": 60000,
}
TEST_TIMEOUT_SECONDS = 120
DECISIONS = ("approved", "edited", "rejected")
LIST_FIELDS = {"investigations", "fix_attempts", "recheck_results"}   # agents add one entry per job
VERIFIED, NEEDS_PERSON, REJECTED, NOT_PROCESSED = (
    "verified_awaiting_approval", "needs_a_person", "rejected", "not_processed")
EVENT = re.compile(r"^[a-z][a-z0-9_]*$")


class RunStopped(Exception):
    """The run must stop (a limit, a failed step, or a safety problem). The message says why."""


class CapHit(Exception):
    """A run cap was reached before a handoff. The rest of the work becomes not_processed."""


class HandoffFailed(Exception):
    """An agent failed, or its output was not accepted. Nothing from it was written to the state."""


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _write_json(path: str, data) -> None:
    temp = path + ".tmp"
    with open(temp, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(data, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
    os.replace(temp, path)


def _read_json(path: str):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _ai_model() -> dict:
    """The model and endpoint are .env settings recorded in every run. None is approved yet."""
    values: dict[str, str] = {}
    env_path = os.path.join(ROOT, ".env")
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as handle:
            for line in handle:
                key, sep, value = line.strip().partition("=")
                if sep and not key.startswith("#"):
                    values[key.strip()] = value.strip()
    return {"name": values.get("AI_MODEL_NAME", "none (offline stand-in, no AI model)"),
            "version": values.get("AI_MODEL_VERSION", "n/a"),
            "endpoint": values.get("AI_MODEL_ENDPOINT", "none")}


class Workflow:
    def __init__(self, agents: dict | None = None, out_root: str | None = None) -> None:
        self.agents = agents or {"auditor": offline_agents.run_auditor,
                                 "investigator": offline_agents.run_investigator,
                                 "fixer_validator": offline_agents.run_fixer_validator}
        self.out_root = out_root or os.path.join(ROOT, "out")
        self.state: dict = {}
        self.meta: dict = {}
        self.run_dir = ""
        self.last_error = ""
        self._t0 = time.monotonic()

    # ------------------------------------------------------------------ small helpers
    @property
    def policy(self) -> dict:
        return self.state["input"]["policy"]

    def _elapsed(self) -> float:
        return self.meta.get("elapsed_before", 0.0) + (time.monotonic() - self._t0)

    def _log(self, actor: str, event: str, detail: str, finding_id: str | None = None) -> None:
        log = self.state["audit_log"]
        entry = {"seq": len(log) + 1, "timestamp": _now(), "actor": actor, "event": event, "detail": detail}
        if finding_id:
            entry["finding_id"] = finding_id
        log.append(entry)

    def _save(self, label: str) -> None:
        """state.json after every handoff (and each setup step), plus a numbered copy."""
        self.meta["snapshots"] = self.meta.get("snapshots", 0) + 1
        self.state["counters"]["elapsed_seconds"] = round(self._elapsed(), 2)
        _write_json(os.path.join(self.run_dir, "state.json"), self.state)
        _write_json(os.path.join(self.run_dir, "states", f"{self.meta['snapshots']:02d}_{label}.json"), self.state)
        _write_json(os.path.join(self.run_dir, "run_meta.json"), self.meta)

    def _check_state(self) -> None:
        problems = validate.schema_errors("state", self.state) or validate.check_state(self.state, None)
        if problems:
            raise RunStopped("the shared state is not valid, so no agent is started: " + "; ".join(problems[:3]))

    def _next_run_id(self) -> str:
        os.makedirs(self.out_root, exist_ok=True)
        numbers = [int(n[4:]) for n in os.listdir(self.out_root) if n.startswith("run-") and n[4:].isdigit()]
        return f"run-{max(numbers, default=0) + 1:03d}"

    # ------------------------------------------------------------------ the run
    def start(self, source_folder: str, rules_file: str, policy: dict | None = None) -> dict:
        """Steps 1 to 5. Stops at step 5 and waits for a person (call resume() after the decisions)."""
        run_id = self._next_run_id()
        self.run_dir = os.path.join(self.out_root, run_id)
        os.makedirs(os.path.join(self.run_dir, "states"))
        self.state = {
            "run_id": run_id,
            "input": {"source_folder": os.path.abspath(source_folder), "rules_file": os.path.abspath(rules_file),
                      "policy": {**DEFAULT_POLICY, **(policy or {})}},
            "counters": {"steps": 0, "ai_calls": 0, "tokens": {"input": 0, "output": 0}, "elapsed_seconds": 0},
            "handoff_log": [], "cap_hit": None, "ai_model": _ai_model(), "sensitive_items_hidden": 0,
            "finding_status": [], "approvals": [], "audit_log": [], "originals_unchanged": None,
        }
        self.meta = {"run_id": run_id, "phase": "running", "snapshots": 0, "elapsed_before": 0.0}
        self._t0 = time.monotonic()
        self._log("orchestrator", "run_started", f"source {self.state['input']['source_folder']}")
        try:
            self._check_state()
            self._save("start")
            self._step1_validate_rules()
            self._step2_temporary_copy()
            self._step3_audit()
            self._step4_findings()
            self._step5_review_queue()
        except RunStopped as stop:
            self._stop(stop)
        return self.state

    def _stop(self, stop: RunStopped) -> None:
        self._log("orchestrator", "run_stopped", str(stop))
        if self.state.get("originals_unchanged") is False:
            self._log("orchestrator", "alert_original_files_changed", "an original file was touched; run stopped")
        self.meta["phase"] = "stopped"
        self.meta["stop_reason"] = str(stop)
        self._save("stopped")
        _write_json(os.path.join(self.run_dir, "report_partial.json"), {
            "stopped": str(stop), "originals_unchanged": self.state.get("originals_unchanged"),
            "finding_status": self.state.get("finding_status", []), "audit_log": self.state["audit_log"]})

    # ------------------------------------------------------------------ step 1 and 2
    def _step1_validate_rules(self) -> None:
        path = self.state["input"]["rules_file"]
        try:
            with open(path, "rb") as handle:
                raw = handle.read()
            rules = json.loads(raw)
        except (OSError, ValueError) as exc:
            raise RunStopped(f"step 1: the rules file cannot be read: {exc}") from None
        problems = validate.schema_errors("rules", rules) or validate.check_rules(rules)
        if problems:
            raise RunStopped("step 1: the rules file is not valid: " + "; ".join(problems[:3]))
        self.state["rules"] = rules
        self.state["rules_file_version"] = "sha256:" + hashlib.sha256(raw).hexdigest()
        self._log("orchestrator", "rules_validated",
                  f"{len(rules['rules'])} rules, version {self.state['rules_file_version'][:19]}...")
        self._save("rules_validated")

    def _step2_temporary_copy(self) -> None:
        source = self.state["input"]["source_folder"]
        try:
            self.meta["originals_hash"] = hash_originals(source)    # fingerprint BEFORE anything else
            info = make_temp_copy(source, self.state["input"]["rules_file"])
        except Exception as exc:  # noqa: BLE001 - any failure here stops the run (canvas section 9)
            raise RunStopped(f"step 2: the temporary copy could not be made: {exc}") from None
        self.meta["temp_run_dir"] = info["run_dir"]
        self.state["workspace"] = {"path": info["workspace"], "original_root": info["original_root"]}
        self._log("orchestrator", "temporary_copy_made",
                  f"{len(self.meta['originals_hash'])} original files fingerprinted; copy made outside the project")
        self._save("temporary_copy")

    # ------------------------------------------------------------------ the handoff (the only way an agent runs)
    def _cap_reached(self) -> str | None:
        c, p = self.state["counters"], self.policy
        if self._elapsed() > p["time_cap_seconds"]:
            return "time"
        if c["steps"] >= p["step_cap"]:
            return "steps"
        if c["ai_calls"] >= p["ai_call_cap"]:
            return "ai_calls"
        if c["tokens"]["input"] >= p["token_cap_input"]:
            return "tokens_input"
        if c["tokens"]["output"] >= p["token_cap_output"]:
            return "tokens_output"
        return None

    def _handoff(self, agent: str, job_name: str, finding_id: str | None, job: dict) -> dict:
        """One orchestrator-to-agent handoff = one step. Validates the state BEFORE (input) and the agent's
        output AFTER (against schemas/ and field ownership), then merges it. Returns the accepted output."""
        cap = self._cap_reached()
        if cap:
            self.state["cap_hit"] = cap
            self._log("orchestrator", "cap_hit", f"{cap}: no more handoffs; the rest is not_processed", finding_id)
            raise CapHit(cap)
        self._check_state()                                              # input is valid before the agent starts
        step = self.state["counters"]["steps"] + 1
        entry = {"step": step, "timestamp": _now(), "agent": agent, "job": job_name, "finding_id": finding_id,
                 "wrote": [], "result": "ok"}
        try:
            output = self.agents[agent]({"job": job_name, **job})
        except AgentError as exc:
            return self._failed(entry, "agent_failed", f"{agent} failed: {exc}", finding_id)
        except Exception as exc:  # noqa: BLE001 - an agent must never crash the run
            return self._failed(entry, "agent_failed", f"{agent} failed unexpectedly ({type(exc).__name__})", finding_id)
        problem = self._accept(agent, output)
        if problem:
            return self._failed(entry, "invalid_output", f"{agent} output rejected: {problem}", finding_id)

        usage = output.get("usage", {})
        c = self.state["counters"]
        c["ai_calls"] += usage.get("ai_calls", 0)
        c["tokens"]["input"] += usage.get("tokens_in", 0)
        c["tokens"]["output"] += usage.get("tokens_out", 0)
        self.state["sensitive_items_hidden"] += usage.get("sensitive_items_hidden", 0)
        for note in output.get("notes", []):
            event = note["event"] if EVENT.match(str(note.get("event", ""))) else "agent_note"
            self._log(agent, event, str(note.get("detail", ""))[:300], finding_id)
        entry["wrote"] = sorted(k for k in output if k not in ("notes", "usage"))
        self.state["counters"]["steps"] = step          # the step count and the handoff log move together
        self.state["handoff_log"].append(entry)
        self._log(agent, f"{job_name}_done", "wrote " + ", ".join(entry["wrote"]), finding_id)
        self._check_state()
        self._save(f"{step:02d}_{agent}_{job_name}" if finding_id is None else f"{step:02d}_{agent}_{job_name}_{finding_id}")
        return output

    def _failed(self, entry: dict, result: str, detail: str, finding_id: str | None) -> dict:
        entry["result"] = result
        self.state["counters"]["steps"] = entry["step"]
        self.state["handoff_log"].append(entry)
        self._log("orchestrator", result, detail[:300], finding_id)
        self._save(f"{entry['step']:02d}_{entry['agent']}_{result}")
        raise HandoffFailed(detail)

    def _accept(self, agent: str, output: object) -> str | None:
        """None if the output may be merged, else the reason it is rejected. The state is changed only here,
        and only after every check passed, so a rejected output leaves no trace in the state."""
        if not isinstance(output, dict):
            return "the output is not a JSON object"
        owned = {n for n, s in validate.SCHEMAS["state"]["properties"].items() if s["x-owner"] == agent}
        fields = {k: v for k, v in output.items() if k not in ("notes", "usage")}
        foreign = sorted(set(fields) - owned)
        if foreign:
            return f"it wrote fields it does not own: {', '.join(foreign)}"
        merged = copy.deepcopy(self.state)
        for name, value in fields.items():
            if name in LIST_FIELDS:
                merged.setdefault(name, []).extend(value)
            else:
                merged[name] = value
        problems = validate.schema_errors("state", merged)
        if not problems:
            problems = validate.check_state(merged, {agent: list(fields)})
        if not problems and "candidate_findings" in fields:
            problems = self._check_evidence(merged["candidate_findings"])
        if problems:
            return "; ".join(problems[:2])
        self.state = merged
        return None

    def _check_evidence(self, candidates: list[dict]) -> list[str]:
        """Every finding must show file, line and code that really are in the project."""
        problems = []
        root = self.state["input"]["source_folder"]
        for i, c in enumerate(candidates):
            shown = read_file(root, c["file"])["response"]
            if not shown["ok"]:
                problems.append(f"candidate_findings/{i}: {c['file']} cannot be read")
                continue
            lines = shown["result"]["content"].splitlines()
            if c["evidence"]["quoted_code"].strip() != (lines[c["line"] - 1].strip() if c["line"] <= len(lines) else ""):
                problems.append(f"candidate_findings/{i}: quoted_code is not at {c['file']} line {c['line']}")
        return problems

    # ------------------------------------------------------------------ step 3: the Auditor
    def _step3_audit(self) -> None:
        state = self.state
        try:
            self._handoff("auditor", "audit", None, {
                "source_folder": state["input"]["source_folder"], "rules_file": state["input"]["rules_file"],
                "rules": state["rules"], "policy": state["input"]["policy"]})
        except CapHit:
            raise RunStopped("step 3: a run limit was reached before the audit") from None
        except HandoffFailed as exc:
            raise RunStopped(f"step 3: the audit failed, so the run stops: {exc}") from None
        if self.state["file_list"]["truncated"]:
            self.state["cap_hit"] = "files"
            self._log("orchestrator", "cap_hit", "files: the file cap cut the list short; files beyond it were not scanned")
        found = self.state["candidate_findings"]
        self._log("orchestrator", "findings_ranked", f"{len(found)} findings with proof, "
                  f"{len(self.state['dropped_findings'])} dropped for missing proof")

    # ------------------------------------------------------------------ step 4: per finding
    def _status(self, finding_id: str, status: str, reason: str | None) -> None:
        rows = [r for r in self.state["finding_status"] if r["finding_id"] != finding_id]
        rows.append({"finding_id": finding_id, "status": status, "reason": reason})
        self.state["finding_status"] = sorted(rows, key=lambda r: r["finding_id"])
        self._log("orchestrator", "status_set", f"{status}" + (f": {reason}" if reason else ""), finding_id)

    def _step4_findings(self) -> None:
        findings = self.state["candidate_findings"]
        if not findings:
            self.state["outcome"] = "safe_nothing_to_report"
            self._log("orchestrator", "nothing_found", "no finding had proof; the run ends as safe_nothing_to_report")
            return
        self.state["outcome"] = "findings_reported"
        self._baseline_done = False
        stopped_by = None
        for finding in findings:                                  # already ranked by the Auditor
            fid = finding["finding_id"]
            if stopped_by:
                self._status(fid, NOT_PROCESSED, f"a run limit stopped the run first ({stopped_by})")
                continue
            try:
                self._one_finding(finding)
            except CapHit as cap:
                stopped_by = str(cap)
                self._status(fid, NOT_PROCESSED, f"a run limit stopped the run first ({stopped_by})")
            except HandoffFailed as exc:
                self._status(fid, NEEDS_PERSON, f"an agent step failed or was rejected: {str(exc)[:160]}")
        self._save("findings_processed")

    def _rule(self, finding: dict) -> dict:
        return next(r for r in self.state["rules"]["rules"] if r["id"] == finding["rule_id"])

    def _one_finding(self, finding: dict) -> None:
        """Decision order for one finding (AGENTS.md section 5)."""
        fid = finding["finding_id"]
        rule = self._rule(finding)
        # 1. limits are checked inside every handoff. 2. proof: candidate_findings already passed the evidence check.
        # 3. tests before any fix
        if not self._baseline_done:
            self._handoff("fixer_validator", "baseline_tests", None, {
                "workspace": self.state["workspace"]["path"], "test_command": self.policy["test_command"],
                "test_timeout_seconds": TEST_TIMEOUT_SECONDS})
            self._baseline_done = True
        baseline = self.state["baseline_tests"]["outcome"]
        if baseline != "pass":
            self._status(fid, NEEDS_PERSON, "no tests exist, so a fix cannot be verified" if baseline == "none"
                         else "the tests already fail before any change")
            return
        # 4. unclear cause or redesign
        self._handoff("investigator", "investigate", fid, {
            "source_folder": self.state["input"]["source_folder"], "finding": finding,
            "file_list": self.state["file_list"]})
        inv = next(i for i in self.state["investigations"] if i["finding_id"] == fid)
        if not inv["fixable"]:
            self._status(fid, NEEDS_PERSON, inv["handoff_reason"])
            return
        # 5. the rule's fix setting
        if not rule["fix_allowed"]:
            self._status(fid, NEEDS_PERSON, "fix not allowed")
            return
        # 6. fix, test, one retry, then rejected
        source = read_file(self.state["workspace"]["path"], finding["file"])["response"]["result"]["content"]
        reason_last = None
        for attempt in range(1, self.policy["max_retries"] + 2):
            self._handoff("fixer_validator", "fix", fid, {
                "workspace": self.state["workspace"]["path"], "finding": finding, "investigation": inv,
                "source": source, "attempt": attempt, "baseline": baseline,
                "test_command": self.policy["test_command"], "test_timeout_seconds": TEST_TIMEOUT_SECONDS,
                "previous_failure": reason_last})
            tried = [a for a in self.state["fix_attempts"] if a["finding_id"] == fid and a["attempt"] == attempt][-1]
            self._handoff("auditor", "recheck", fid, {
                "workspace": self.state["workspace"]["path"], "rules_file": self.state["input"]["rules_file"],
                "files": tried["files_changed"] or [finding["file"]], "finding_id": fid, "attempt": attempt})
            clear = next(r for r in self.state["recheck_results"]
                         if r["finding_id"] == fid and r["attempt"] == attempt)["clear"]
            # Verified only when the tests pass AND the re-check is clear. The agent's decision is only advice.
            if tried["patch_diff"] and tried["tests"]["after"] == "pass" and tried["recheck"] == "clear" and clear:
                self._status(fid, VERIFIED, None)
                return
            reason_last = tried["residual_risk"]
            self._log("orchestrator", "fix_failed", f"attempt {attempt}: {reason_last}", fid)
            if attempt <= self.policy["max_retries"]:
                self._undo_attempt(finding, tried)
        self._status(fid, REJECTED, "the fix failed after the one retry: " + (reason_last or "no reason given"))

    def _undo_attempt(self, finding: dict, tried: dict) -> None:
        """Put the temporary copy back as it was before a failed attempt (reverse patch), so the retry starts clean."""
        if not tried["patch_diff"] or not tried["files_changed"]:
            return
        reverse = []
        for line in tried["patch_diff"].splitlines():
            if line.startswith("--- a/"):
                reverse.append("--- a/" + line[6:])
            elif line.startswith("+++ b/"):
                reverse.append("+++ b/" + line[6:])
            elif line.startswith("@@"):
                m = re.match(r"@@ -(\d+),(\d+) \+(\d+),(\d+) @@", line)
                reverse.append(f"@@ -{m.group(3)},{m.group(4)} +{m.group(1)},{m.group(2)} @@" if m else line)
            elif line.startswith("-"):
                reverse.append("+" + line[1:])
            elif line.startswith("+"):
                reverse.append("-" + line[1:])
            else:
                reverse.append(line)
        undone = apply_patch(self.state["workspace"]["path"], "\n".join(reverse) + "\n")["response"]
        self._log("orchestrator", "attempt_undone" if undone["ok"] else "attempt_undo_failed",
                  "the temporary copy was restored before the retry" if undone["ok"]
                  else "the failed attempt could not be undone: " + undone["error"]["message"][:120], finding["finding_id"])
