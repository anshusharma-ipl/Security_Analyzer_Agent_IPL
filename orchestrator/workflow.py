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

import kill_checks  # noqa: E402  (canvas section 16: one automatic check per immediate kill criterion)
import validate  # noqa: E402  (schema checks and the code checks a schema cannot state)
from agents import AgentError, offline_agents  # noqa: E402
from tools import _containment  # noqa: E402
from tools._mask import Masker  # noqa: E402
from tools._safety import SafetyError, is_inside  # noqa: E402
from tools._schema import SchemaError  # noqa: E402
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


class KillStop(RunStopped):
    """A kill criterion fired (canvas section 16). The run is stopped and an alert is raised (alert.json)."""

    def __init__(self, criterion: str, detail: str) -> None:
        super().__init__(f"kill criterion {criterion}: {detail}")
        self.criterion, self.detail = criterion, detail


class StillWaiting(Exception):
    """The review is not complete or not usable yet. The run is NOT stopped; fix review_queue.json and finish again."""


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


def _with_guard(method):
    """Run a public step (start, finish) with the network guard installed, and always take it off again."""
    def wrapper(self, *args, **kwargs):
        self.guard = kill_checks.NetworkGuard()
        self.guard.install()
        try:
            return method(self, *args, **kwargs)
        finally:
            self.guard.uninstall()
    wrapper.__name__, wrapper.__doc__ = method.__name__, method.__doc__
    return wrapper


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
        self.guard = None
        self._last_handoff: tuple | None = None          # (agent, its output) of the last accepted handoff

    # ------------------------------------------------------------------ small helpers
    @property
    def policy(self) -> dict:
        return self.state["input"]["policy"]

    def _elapsed(self) -> float:
        return self.meta.get("elapsed_before", 0.0) + (time.monotonic() - self._t0)

    def _log(self, actor: str, event: str, detail: str, finding_id: str | None = None) -> None:
        log = self.state["audit_log"]
        masker = Masker()
        detail = masker.line(detail)                      # a secret or personal value never reaches the log
        self.state["sensitive_items_hidden"] += masker.hidden
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

    def _kill(self, point: str, output=None) -> None:
        """The eight immediate kill checks (kill_checks.py). A criterion that fires is logged and stops the run."""
        base = self.meta.get("kill_baseline")
        if not base:
            return
        try:
            kill_checks.check(point, base, self.state, self.meta, self.run_dir, output=output, guard=self.guard)
        except kill_checks.KillSwitch as fired:
            self._log("orchestrator", f"alert_kill_{fired.criterion}", fired.detail)
            raise KillStop(fired.criterion, fired.detail) from None

    def _check_state(self) -> None:
        problems = validate.schema_errors("state", self.state) or validate.check_state(self.state, None)
        if problems:
            raise RunStopped("the shared state is not valid, so no agent is started: " + "; ".join(problems[:3]))

    def _next_run_id(self) -> str:
        os.makedirs(self.out_root, exist_ok=True)
        numbers = [int(n[4:]) for n in os.listdir(self.out_root) if n.startswith("run-") and n[4:].isdigit()]
        return f"run-{max(numbers, default=0) + 1:03d}"

    # ------------------------------------------------------------------ the run
    @_with_guard
    def start(self, source_folder: str, rules_file: str, policy: dict | None = None) -> dict:
        """Steps 1 to 5. Stops at step 5 and waits for a person (call resume() after the decisions)."""
        if is_inside(os.path.abspath(source_folder), os.path.abspath(self.out_root)):
            raise ValueError("the out folder is inside the project folder; the end-of-run check would see the "
                             "report files as changes to the originals. Choose an out folder outside the project.")
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
            if self._step5_review_queue():
                self._finish()          # nothing is waiting for a person, so go straight to steps 6 and 7
        except RunStopped as stop:
            self._stop(stop)
        return self.state

    @classmethod
    def load(cls, run_dir: str, agents: dict | None = None) -> "Workflow":
        """Re-open a run that is waiting for a person (a new process, a day later)."""
        flow = cls(agents, out_root=os.path.dirname(os.path.abspath(run_dir)))
        flow.run_dir = os.path.abspath(run_dir)
        flow.state = _read_json(os.path.join(flow.run_dir, "state.json"))
        flow.meta = _read_json(os.path.join(flow.run_dir, "run_meta.json"))
        flow.meta["elapsed_before"] = flow.state["counters"]["elapsed_seconds"]   # waiting for a person is not run time
        flow._t0 = time.monotonic()
        return flow

    @_with_guard
    def finish(self) -> dict:
        """After the person has filled in review_queue.json: apply the decisions, then steps 6 and 7.
        Raises StillWaiting (the run is NOT stopped) if the review is incomplete or was altered."""
        if self.meta.get("phase") != "waiting_for_review":
            raise RunStopped(f"this run is not waiting for a review (phase: {self.meta.get('phase')})")
        try:
            self._finish()
        except RunStopped as stop:
            self._stop(stop)
        return self.state

    def _stop(self, stop: RunStopped) -> None:
        self._log("orchestrator", "run_stopped", str(stop))
        if self.state.get("originals_unchanged") is False:
            self._log("orchestrator", "alert_original_files_changed", "an original file was touched; run stopped")
        if isinstance(stop, KillStop):
            self.meta["alert"] = {"criterion": stop.criterion, "detail": stop.detail, "time": _now()}
            _write_json(os.path.join(self.run_dir, "alert.json"), self.meta["alert"])
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
        banned = _containment.forbidden_command(self.policy["test_command"])
        if banned:
            self._log("orchestrator", "alert_forbidden_command", f"test_command refused: {banned}")
            raise RunStopped(f"step 1: test_command is not allowed: {banned}")
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
        self.meta["kill_baseline"] = kill_checks.take_baseline(source, info["run_dir"])
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
        self._drain_events(agent, finding_id)             # events left over from before this handoff are not this agent's
        try:
            output = self.agents[agent]({"job": job_name, **job})
        except _containment.ContainmentViolation as exc:
            network = isinstance(exc, _containment.NetworkViolation)
            criterion = "network_not_approved" if network else "write_outside_workspace"
            self._drain_events(agent, finding_id)
            if not network:
                self._log("orchestrator", "alert_write_outside_copy", f"{agent}: {exc}", finding_id)
            self._log("orchestrator", f"alert_kill_{criterion}", f"{agent}: {exc}", finding_id)
            raise KillStop(criterion, f"{agent}: {exc}") from None
        except AgentError as exc:
            return self._failed(entry, "agent_failed", f"{agent} failed: {exc}", finding_id)
        except Exception as exc:  # noqa: BLE001 - an agent must never crash the run
            return self._failed(entry, "agent_failed", f"{agent} failed unexpectedly ({type(exc).__name__})", finding_id)
        self._kill("handoff", output)
        self._drain_events(agent, finding_id)
        if agent == "auditor" and isinstance(output, dict) and isinstance(output.get("candidate_findings"), list):
            output = self._drop_unproven(output, finding_id)
        signature = self._signature(output)
        if (agent, signature) == self._last_handoff:
            self._log("orchestrator", "alert_loop_detected",
                      f"{agent} was run twice in a row and gave the same result, so there is no new state", finding_id)
            raise RunStopped(f"loop: {agent} ran twice in a row with no new state. The run is stopped")
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
        self._last_handoff = (agent, signature)
        self.state["counters"]["steps"] = step          # the step count and the handoff log move together
        self.state["handoff_log"].append(entry)
        self._log(agent, f"{job_name}_done", "wrote " + ", ".join(entry["wrote"]), finding_id)
        self._check_state()
        self._save(f"{agent}_{job_name}" if finding_id is None else f"{agent}_{job_name}_{finding_id}")
        return output

    @staticmethod
    def _signature(output: object) -> str:
        """What an agent handed over, without the bookkeeping (usage, notes). Same signature twice = no new state."""
        body = {k: v for k, v in output.items() if k not in ("usage", "notes")} if isinstance(output, dict) else output
        return json.dumps(body, sort_keys=True, default=str)

    def _drop_unproven(self, output: dict, finding_id: str | None) -> dict:
        """A candidate must show file, line and quoted code that really are in the project. One that does not is
        dropped (logged, never counted) and the rest go on; ids and ranks are renumbered in order."""
        kept, dropped = [], list(output.get("dropped_findings", []))
        for c in output["candidate_findings"]:
            ev = c.get("evidence") if isinstance(c, dict) else None
            proven = bool(isinstance(ev, dict) and isinstance(ev.get("file"), str) and ev["file"]
                          and isinstance(ev.get("line"), int) and not isinstance(ev.get("line"), bool) and ev["line"] >= 1
                          and isinstance(ev.get("quoted_code"), str) and ev["quoted_code"].strip()
                          and c.get("file") == ev["file"] and c.get("line") == ev["line"])
            reason = "missing file, line or quoted code"
            if proven:
                proven = not self._check_evidence([c])
                reason = "the quoted code is not at that file and line"
            if proven:
                kept.append(c)
                continue
            where = c if isinstance(c, dict) else {}
            dropped.append({"rule_id": str(where.get("rule_id") or "unknown"), "file": str(where.get("file") or "unknown"),
                            "line": where.get("line") if isinstance(where.get("line"), int) else None, "reason": reason})
            self._log("orchestrator", "finding_dropped", f"{where.get('rule_id')} {where.get('file')}: {reason}", finding_id)
        if len(kept) == len(output["candidate_findings"]):
            return output
        for n, c in enumerate(kept, 1):
            c["finding_id"], c["rank"] = f"F{n:03d}", n
        return {**output, "candidate_findings": kept, "dropped_findings": dropped}

    def _drain_events(self, agent: str, finding_id: str | None) -> None:
        """Blocked tool calls recorded by tools/_containment go into the decision log."""
        for event, detail in _containment.drain_events():
            self._log("orchestrator", event, detail, finding_id)

    def _failed(self, entry: dict, result: str, detail: str, finding_id: str | None) -> dict:
        entry["result"] = result
        self.state["counters"]["steps"] = entry["step"]
        self.state["handoff_log"].append(entry)
        self._log("orchestrator", result, detail[:300], finding_id)
        self._save(f"{entry['agent']}_{result}")
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
            shown_line = lines[c["line"] - 1].strip() if 1 <= c["line"] <= len(lines) else ""
            same = lambda s: validate.PLACEHOLDER.sub(lambda m: m.group(0).split("_")[0] + ">", s.strip())  # noqa: E731
            if same(c["evidence"]["quoted_code"]) != same(shown_line):
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
        if finding["detected_by"] == "ai_model" and finding["confidence"] < self.policy["confidence_gate"]:
            self._status(fid, NEEDS_PERSON, f"low confidence: found by the AI model alone with confidence "
                         f"{finding['confidence']}, below the gate {self.policy['confidence_gate']}")
            return
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
            if not tried["patch_diff"]:                       # nothing was written, so a retry would be identical
                self._status(fid, NEEDS_PERSON, "the fixer could not write a patch for this finding")
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

    # ------------------------------------------------------------------ step 5: the review queue
    def _findings_by_id(self) -> dict:
        return {c["finding_id"]: c for c in self.state.get("candidate_findings", [])}

    def _verified_attempt(self, fid: str) -> dict:
        """The kept attempt of a verified finding: the last one that passed tests and the re-check."""
        return [a for a in self.state["fix_attempts"]
                if a["finding_id"] == fid and a["patch_diff"] and a["tests"]["after"] == "pass"
                and a["recheck"] == "clear"][-1]

    def _step5_review_queue(self) -> bool:
        """Write review_queue.json and wait. Returns True when nothing needs a person's decision."""
        by_id = self._findings_by_id()
        status = {r["finding_id"]: r for r in self.state["finding_status"]}
        proposals, also = [], []
        for fid, finding in sorted(by_id.items()):
            row = status.get(fid)
            if row is None:
                continue
            if row["status"] == VERIFIED:
                attempt = self._verified_attempt(fid)
                inv = next(i for i in self.state["investigations"] if i["finding_id"] == fid)
                proposals.append({
                    "finding_id": fid, "rule_id": finding["rule_id"], "severity": finding["severity"],
                    "confidence": finding["confidence"], "file": finding["file"], "line": finding["line"],
                    "evidence": finding["evidence"], "traced_cause": inv["traced_cause"],
                    "patch_diff": attempt["patch_diff"], "tests": attempt["tests"], "recheck": attempt["recheck"],
                    "residual_risk": attempt["residual_risk"],
                    "decision": None, "reason": None, "reviewer": None, "edited_patch_diff": None})
            else:
                package = self._finding_entry(fid, finding, row)
                also.append({"finding_id": fid, "rule_id": finding["rule_id"], "file": finding["file"],
                             "line": finding["line"], "status": row["status"], "reason": row["reason"],
                             "severity": package["severity"], "confidence": package["confidence"],
                             "evidence": package["evidence"], "traced_cause": package.get("traced_cause"),
                             "patch_diff": package["patch_diff"], "tests": package["tests"],
                             "recheck": package["recheck"], "residual_risk": package["residual_risk"]})
        queue = {"run_id": self.state["run_id"],
                 "note": "For each proposal set decision to approved, edited or rejected, and fill in reviewer and "
                         "reason (reason is required for edited and rejected). For edited, also put your own "
                         "unified diff in edited_patch_diff. Change nothing else. Nothing is applied automatically.",
                 "proposals": proposals, "also_reported": also}
        self._check_queue_schema(queue)
        _write_json(os.path.join(self.run_dir, "review_queue.json"), queue)
        self.meta["queue_digest"] = self._digest(queue)
        self._log("orchestrator", "review_queue_written",
                  f"{len(proposals)} proposals waiting for a person; {len(also)} findings need no decision")
        if not proposals:
            self._save("no_proposals")
            return True
        self.meta["phase"] = "waiting_for_review"
        self._log("orchestrator", "waiting_for_person", "the run waits for approve / edit / reject; nothing is applied")
        self._save("waiting_for_review")
        return False

    @staticmethod
    def _digest(queue: dict) -> str:
        """Fingerprint of everything in the queue EXCEPT the four decision fields, so an edit to a patch, a status
        or the evidence is noticed."""
        frozen = copy.deepcopy(queue)
        for p in frozen["proposals"]:
            for key in ("decision", "reason", "reviewer", "edited_patch_diff"):
                p.pop(key, None)
        frozen.pop("note", None)
        return hashlib.sha256(json.dumps(frozen, sort_keys=True).encode("utf-8")).hexdigest()

    @staticmethod
    def _check_queue_schema(queue: dict) -> None:
        problems = validate.schema_errors("review_queue", queue)
        if problems:
            raise StillWaiting("review_queue.json is not valid: " + "; ".join(problems[:3]))

    # ------------------------------------------------------------------ after the person has decided
    def _read_decisions(self) -> list[dict]:
        path = os.path.join(self.run_dir, "review_queue.json")
        try:
            queue = _read_json(path)
        except (OSError, ValueError) as exc:
            raise StillWaiting(f"review_queue.json cannot be read: {exc}") from None
        self._check_queue_schema(queue)
        if queue["run_id"] != self.state["run_id"]:
            raise StillWaiting("review_queue.json belongs to another run")
        if self._digest(queue) != self.meta.get("queue_digest"):
            raise StillWaiting("review_queue.json was changed outside the four decision fields "
                               "(decision, reason, reviewer, edited_patch_diff); restore it and try again")
        missing = [p["finding_id"] for p in queue["proposals"] if p["decision"] is None]
        if missing:
            raise StillWaiting("still waiting for a decision on: " + ", ".join(missing))
        return queue["proposals"]

    def _finish(self) -> None:
        if self.meta.get("phase") == "waiting_for_review":
            self._apply_decisions(self._read_decisions())
        self._step6_verify_originals()
        self._step7_report()

    def _apply_decisions(self, proposals: list[dict]) -> None:
        patches = []
        for p in proposals:
            fid, decision = p["finding_id"], p["decision"]
            diff = p["patch_diff"]
            if decision == "edited":
                diff = self._recheck_edit(p)
            self.state["approvals"].append({
                "finding_id": fid, "decision": decision, "reason": p["reason"] or "", "reviewer": p["reviewer"],
                "timestamp": _now()})
            self._log("person", f"fix_{decision}", f"{p['reviewer']}: {p['reason'] or 'no reason given'}", fid)
            if decision == "rejected":
                self._status(fid, REJECTED, "a person rejected the fix: " + p["reason"])
            else:
                patches.append((fid, diff))
        self.meta["approved_patches"] = patches
        self.meta["phase"] = "decided"

    def _recheck_edit(self, proposal: dict) -> str:
        """A person's own diff is held to the same bar as ours: it applies, the tests pass, the re-check is clear.
        It is tried on a FRESH temporary copy so it cannot be mixed up with the agent's fix."""
        fid, diff = proposal["finding_id"], proposal["edited_patch_diff"]
        fresh = make_temp_copy(self.state["input"]["source_folder"], self.state["input"]["rules_file"])
        self.meta.setdefault("extra_run_dirs", []).append(fresh["run_dir"])
        ws = fresh["workspace"]
        problem = None
        applied = apply_patch(ws, diff)["response"]
        if not applied["ok"]:
            problem = "the edited patch does not apply: " + applied["error"]["message"][:120]
        else:
            ran = run_tests(ws, self.policy["test_command"], TEST_TIMEOUT_SECONDS)["response"]
            if not ran["ok"] or ran["result"]["outcome"] != "pass":
                problem = "the tests do not pass with the edited patch"
            else:
                checked = request_recheck(ws, applied["result"]["files_changed"])["response"]
                if not checked["ok"] or not checked["result"]["clear"]:
                    problem = "the re-check is not clear with the edited patch"
        if problem:
            self._log("orchestrator", "edit_not_verified", problem, fid)
            raise StillWaiting(f"{fid}: {problem}. Fix edited_patch_diff, or choose rejected, and finish again.")
        self._log("orchestrator", "edit_verified", "the edited patch applies, the tests pass and the re-check is clear", fid)
        return diff

    # ------------------------------------------------------------------ step 6 and 7
    def _step6_verify_originals(self) -> None:
        check = verify_originals(self.state["input"]["source_folder"], self.meta["originals_hash"])
        self.state["originals_unchanged"] = check["unchanged"]
        self._log("orchestrator", "originals_verified" if check["unchanged"] else "originals_changed",
                  "no original file was changed, added or removed" if check["unchanged"]
                  else f"changed {check['changed']}, added {check['added']}, removed {check['removed']}")
        self._save("originals_verified")
        if not check["unchanged"]:
            raise RunStopped("step 6: an original file was changed. Stop rule: the run is stopped and an alert is raised")
        with open(self.state["input"]["rules_file"], "rb") as handle:
            if "sha256:" + hashlib.sha256(handle.read()).hexdigest() != self.state["rules_file_version"]:
                self._log("orchestrator", "alert_rules_file_changed", "rules.json changed during the run; run stopped")
                raise RunStopped("step 6: the rules file changed during the run. The run is stopped and an alert is raised")

    def _totals(self) -> dict:
        count = lambda s: sum(1 for r in self.state["finding_status"] if r["status"] == s)  # noqa: E731
        return {"found": len(self.state["finding_status"]), "fixed_and_verified": count(VERIFIED),
                "rejected": count(REJECTED), "needs_a_person": count(NEEDS_PERSON), "remaining": count(NOT_PROCESSED)}

    def _finding_entry(self, fid: str, finding: dict, row: dict) -> dict:
        """Everything a person needs about one finding (canvas section 12 handoff package; also the report row)."""
        state = self.state
        attempts = [a for a in state.get("fix_attempts", []) if a["finding_id"] == fid]
        inv = next((i for i in state.get("investigations", []) if i["finding_id"] == fid), None)
        last = (self._verified_attempt(fid) if row["status"] == VERIFIED else (attempts[-1] if attempts else None))
        entry = {"finding_id": fid, "rule_id": finding["rule_id"], "file": finding["file"],
                 "line": finding["line"], "severity": finding["severity"], "evidence": finding["evidence"],
                 "confidence": finding["confidence"], "detected_by": finding["detected_by"],
                 "status": row["status"],
                 "patch_diff": last["patch_diff"] if last and row["status"] in (VERIFIED, REJECTED) else None,
                 "tests": last["tests"] if last else {"before": state.get("baseline_tests", {}).get("outcome", "none"),
                                                      "after": None},
                 "recheck": last["recheck"] if last else "not_run",
                 "residual_risk": (last["residual_risk"] if last else
                                   "Nothing was changed, so the weak spot is still in the code.")}
        if row["reason"]:
            entry["reason"] = row["reason"]
        if inv and inv["traced_cause"]:
            entry["traced_cause"] = inv["traced_cause"]
        return entry

    def _step7_report(self) -> None:
        state = self.state
        self._kill("end")
        state["totals"] = self._totals()
        leaks = _containment.find_leaks(state["audit_log"])
        if leaks:
            raise RunStopped("step 7: the decision log holds an unmasked value (" + ", ".join(leaks) + "); nothing was written")
        self._log("orchestrator", "decision_log_written", f"{len(state['audit_log'])} entries, written before the report")
        try:
            _write_json(os.path.join(self.run_dir, "decision_log.json"), state["audit_log"])
            written = _read_json(os.path.join(self.run_dir, "decision_log.json"))
            if len(written) != len(state["audit_log"]):
                raise ValueError("the decision log on disk is shorter than the log in memory")
        except (OSError, ValueError) as exc:
            self._log("orchestrator", "alert_kill_audit_incomplete", f"the decision log could not be written whole ({type(exc).__name__})")
            raise KillStop("audit_incomplete", "the decision log could not be written whole") from None

        by_id, status = self._findings_by_id(), {r["finding_id"]: r for r in state["finding_status"]}
        findings = [self._finding_entry(fid, finding, status[fid]) for fid, finding in sorted(by_id.items())]

        report = {
            "outcome": state["outcome"],
            "run": {"rules_file_version": state["rules_file_version"], "ai_model": state["ai_model"],
                    "sensitive_items_hidden": state["sensitive_items_hidden"], "tokens": state["counters"]["tokens"]},
            "totals": state["totals"], "findings": findings, "approvals": state["approvals"],
            "audit_log": state["audit_log"],
        }
        leaks = _containment.find_leaks(report)
        if leaks:
            raise RunStopped("step 7: the report holds an unmasked value (" + ", ".join(leaks) + "); nothing was written")
        problems = validate.schema_errors("output", report)
        if not problems:
            problems = validate.check_output(report, {"project_root": state["input"]["source_folder"],
                                                      "workspace": state["workspace"]["path"]})
        if problems:
            _write_json(os.path.join(self.run_dir, "report_partial.json"), report)
            raise RunStopped("step 7: the report did not pass validation, so only a partial report was written: "
                             + "; ".join(problems[:3]))
        _write_json(os.path.join(self.run_dir, "report.json"), report)
        patches = self.meta.get("approved_patches", [])
        if patches:
            joined = "".join(diff if diff.endswith("\n") else diff + "\n" for _fid, diff in patches)
            with open(os.path.join(self.run_dir, "fixes.patch"), "w", encoding="utf-8", newline="\n") as handle:
                handle.write(joined)
        with open(os.path.join(self.run_dir, "report.md"), "w", encoding="utf-8", newline="\n") as handle:
            handle.write(self._report_text(report, bool(patches)))
        self.meta["phase"] = "done"
        self._save("done")
        for folder in [self.meta.get("temp_run_dir"), *self.meta.get("extra_run_dirs", [])]:
            if folder:
                shutil.rmtree(folder, ignore_errors=True)       # the temporary copies are no longer needed

    @staticmethod
    def _report_text(report: dict, has_patch: bool) -> str:
        t = report["totals"]
        lines = ["# Security Analyzer report", "",
                 f"- outcome: **{report['outcome']}**",
                 f"- rules file version: `{report['run']['rules_file_version']}`",
                 f"- AI model: {report['run']['ai_model']['name']} (endpoint: {report['run']['ai_model']['endpoint']})",
                 f"- sensitive items hidden: {report['run']['sensitive_items_hidden']}",
                 f"- tokens: {report['run']['tokens']['input']} in, {report['run']['tokens']['output']} out",
                 f"- totals: found {t['found']}, fixed and verified {t['fixed_and_verified']}, rejected {t['rejected']}, "
                 f"needs a person {t['needs_a_person']}, remaining {t['remaining']}", ""]
        for f in report["findings"]:
            lines += [f"## {f['finding_id']} {f['rule_id']} {f['file']}:{f['line']} ({f['severity']}): {f['status']}",
                      f"- evidence: `{f['evidence']['quoted_code']}`", f"- confidence: {f['confidence']} ({f['detected_by']})",
                      f"- tests: before {f['tests']['before']}, after {f['tests']['after']}; re-check: {f['recheck']}"]
            if f.get("reason"):
                lines.append(f"- reason: {f['reason']}")
            if f.get("traced_cause"):
                lines.append(f"- traced cause: {f['traced_cause']['explanation']}")
            lines.append(f"- residual risk: {f['residual_risk']}")
            if f["patch_diff"]:
                lines += ["", "```diff", f["patch_diff"].rstrip("\n"), "```"]
            lines.append("")
        lines.append("## Approvals")
        lines += ([f"- {a['finding_id']}: {a['decision']} by {a['reviewer']} ({a['reason'] or 'no reason'})"
                   for a in report["approvals"]] or ["- none"])
        lines += ["", "Nothing was applied to the original folder." + (
            " Approved fixes are in fixes.patch for a person to apply." if has_patch else ""), ""]
        return "\n".join(lines)
