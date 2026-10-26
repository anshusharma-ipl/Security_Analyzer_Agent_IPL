"""Show each decision guardrail firing on a real run (a temp copy of the golden case is the "original").

    python evals/decisions_demo.py
"""
import json
import os
import sys
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

import test_decisions as t  # noqa: E402
from agents import offline_agents  # noqa: E402


class Demo(t.DecisionCase):
    def runTest(self):
        pass

    def show(self, title, flow, note=""):
        print(f"\n{title}")
        if note:
            print(f"   note   : {note}")
        for row in flow.state["finding_status"]:
            print(f"   status : {row['finding_id']} {row['status']}: {row['reason']}")
        attempts = flow.state.get("fix_attempts", [])
        if attempts:
            print("   attempts:", [(a["attempt"], "tests " + str(a["tests"]["after"]), "recheck " + a["recheck"]) for a in attempts])
        queue = self.queue(flow)
        for e in queue["also_reported"]:
            print(f"   queue  : handoff package for {e['finding_id']}: " + ", ".join(
                f"{k}={json.dumps(e[k])[:40]}" for k in ("rule_id", "severity", "confidence", "line", "tests", "recheck")))
            print(f"            evidence={e['evidence']['quoted_code'][:60]!r}; residual_risk={e['residual_risk'][:60]!r}")
        for p in queue["proposals"]:
            print(f"   queue  : proposal {p['finding_id']} waits for a person (not verified here)")


d = Demo()
d.setUp()
d.show("case_08 (no tests)", d.run_flow("case_08_no_tests"))
d.show("case_06 (dependency, DEP-PIN has fix_allowed false)", d.run_flow("case_06_old_library_version"))
d.show("case_07 (redesign: the client sends raw SQL)", d.run_flow("case_07_raw_sql_from_client"))


def model_auditor(job):
    out = offline_agents.run_auditor(job)
    for finding in out.get("candidate_findings", []):
        finding.update(detected_by="ai_model", confidence=0.55)
    return out


d.show("case_11 (low confidence, AI-only finding below the 0.70 gate)",
       d.run_flow("case_11_escalate_no_callers", {"auditor": model_auditor}),
       "SIMULATED: no model is connected, so the Auditor is wrapped to report this finding as a model would (0.55). "
       "Without the wrapper the offline stand-in treats case_11 like case_01 and proposes a fix (known limit).")
with mock.patch.object(offline_agents, "_sqli_patch", t.comment_only_patch):
    d.show("tests pass but the re-check is NOT clear (patch only adds a comment; the rule still matches)",
           d.run_flow("case_01_sqli_fstring"))
with mock.patch.object(offline_agents, "_sqli_patch", t.test_breaking_patch):
    flow = d.run_flow("case_01_sqli_fstring")
d.show("retry cap (the fix breaks the tests; 1 try + 1 retry, then rejected)", flow)
print("   events :", [e["event"] for e in flow.state["audit_log"] if e["event"] in ("fix_failed", "attempt_undone", "status_set")])
d.doCleanups()
