"""Copy what a real (model-backed) run captured into docs_html/data/live_run.json, for the Live run page.

    python docs_html/collect_live_run.py <run folder>        # the folder that holds report.json and state.json

Only fields that describe the run are kept (findings, fixes, test results, trace, approvals, token counts).
Local paths, the source folder and the audit log are left out, so the file is safe to commit.
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


def load(folder: str, name: str) -> dict:
    with open(os.path.join(folder, name), encoding="utf-8") as handle:
        return json.load(handle)


def main(folder: str) -> int:
    report, state = load(folder, "report.json"), load(folder, "state.json")
    attempts: dict[str, list] = {}
    for a in state.get("fix_attempts", []):
        attempts.setdefault(a["finding_id"], []).append(
            {"attempt": a["attempt"], "tests_after": (a.get("tests") or {}).get("after"), "recheck": a.get("recheck"), "decision": a.get("decision")})
    approvals = {a["finding_id"]: {"decision": a["decision"], "reviewer": a.get("reviewer", ""), "timestamp": a.get("timestamp", "")} for a in report.get("approvals", [])}
    findings = []
    for f in report["findings"]:
        findings.append({
            "id": f["finding_id"], "rule": f["rule_id"], "file": f["file"], "line": f["line"], "severity": f["severity"],
            "confidence": f.get("confidence"), "detected_by": f.get("detected_by"), "status": f["status"], "reason": f.get("reason"),
            "quoted_code": (f.get("evidence") or {}).get("quoted_code"), "traced_cause": f.get("traced_cause"),
            "patch_diff": f.get("patch_diff"), "tests": f.get("tests"), "recheck": f.get("recheck"), "residual_risk": f.get("residual_risk"),
            "attempts": attempts.get(f["finding_id"], []), "approval": approvals.get(f["finding_id"]),
        })
    handoffs = [{"step": h["step"], "agent": h["agent"], "job": h["job"], "finding_id": h.get("finding_id"), "result": h["result"]} for h in state["handoff_log"]]
    counters = state["counters"]
    out = {
        "run_id": state["run_id"], "date": state["handoff_log"][0]["timestamp"][:10],
        "model": state["ai_model"]["name"], "endpoint": state["ai_model"].get("endpoint"),
        "ai_calls": counters["ai_calls"], "steps": counters["steps"], "tokens": counters["tokens"],
        "elapsed_seconds": round(counters["elapsed_seconds"]), "cap_hit": state.get("cap_hit"),
        "originals_unchanged": state.get("originals_unchanged"), "baseline_tests": state.get("baseline_tests", {}).get("outcome"),
        "sensitive_items_hidden": state.get("sensitive_items_hidden"), "totals": report["totals"],
        "findings": findings, "handoffs": handoffs,
    }
    path = os.path.join(HERE, "data", "live_run.json")
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(out, handle, indent=1)
        handle.write("\n")
    print(f"wrote {os.path.relpath(path)}: {len(findings)} findings, {len(handoffs)} steps, model {out['model']}")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1]))
