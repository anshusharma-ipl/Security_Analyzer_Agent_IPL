"""Decision guardrails, one test each (canvas sections 10, 12, 13; AGENTS.md sections 5 and 6).

    python -m unittest tests.test_decisions -v

Every run uses a copy of a golden case in a temp folder. Where a case needs a model's judgement that the
offline stand-ins do not have, or a fix that fails in a particular way, the stand-in is wrapped or patched on
purpose, and the test says so.
"""
import copy
import json
import os
import shutil
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import validate  # noqa: E402
from agents import offline_agents  # noqa: E402
from orchestrator.workflow import DEFAULT_POLICY, RunStopped, Workflow  # noqa: E402

RULES = os.path.join(ROOT, "golden", "rules.json")
HONEST = {"auditor": offline_agents.run_auditor, "investigator": offline_agents.run_investigator,
          "fixer_validator": offline_agents.run_fixer_validator}
PACKAGE = ("rule_id", "severity", "confidence", "file", "line", "evidence", "traced_cause", "patch_diff", "tests",
           "recheck", "residual_risk")                                  # canvas section 12 handoff package
USAGE_ZERO = {"ai_calls": 0, "tokens_in": 0, "tokens_out": 0, "sensitive_items_hidden": 0}


def edit_diff(file, text, target, transform):
    """A one-line unified diff: line ``target`` (1-based, at least 2) is rewritten by ``transform``."""
    lines = text.splitlines()
    context = target - 1
    return "\n".join([f"--- a/{file}", f"+++ b/{file}", f"@@ -{context},2 +{context},2 @@", " " + lines[context - 1],
                      "-" + lines[target - 1], "+" + transform(lines[target - 1]), ""])


def comment_only_patch(file, text, line_no):
    """Passes the tests, but the flagged line still matches the rule, so the re-check is not clear."""
    return edit_diff(file, text, line_no, lambda line: line + "  # reviewed")


def test_breaking_patch(file, text, line_no):
    """Parses, but changes what the function returns, so the project's tests fail."""
    return edit_diff(file, text, line_no + 1, lambda line: line.replace("fetchone()", "fetchall()"))


class DecisionCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="saa-decisions-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.runs = 0

    def run_flow(self, case, agents=None, policy=None):
        self.runs += 1
        project = os.path.join(self.tmp, f"project{self.runs}")
        shutil.copytree(os.path.join(ROOT, "golden", case), project, ignore=shutil.ignore_patterns("expected.json"))
        flow = Workflow(agents={**HONEST, **(agents or {})}, out_root=os.path.join(self.tmp, "out"))
        flow.start(project, RULES, policy)
        return flow

    @staticmethod
    def status(flow):
        return {r["finding_id"]: r for r in flow.state["finding_status"]}

    @staticmethod
    def events(flow):
        return [e["event"] for e in flow.state["audit_log"]]

    @staticmethod
    def queue(flow):
        with open(os.path.join(flow.run_dir, "review_queue.json"), encoding="utf-8") as handle:
            return json.load(handle)

    def assert_handoff_package(self, flow, finding_id):
        """The finding sits in review_queue.json with every part of the canvas section 12 package."""
        queue = self.queue(flow)
        self.assertEqual(validate.schema_errors("review_queue", queue), [])
        entry = next(e for e in queue["also_reported"] if e["finding_id"] == finding_id)
        for key in PACKAGE:
            self.assertIn(key, entry, f"handoff package is missing {key}")
        for key in ("file", "line", "quoted_code"):
            self.assertTrue(entry["evidence"][key])
        return entry


class TestDecisions(DecisionCase):
    # -------------------------------------------------------------- evidence
    def test_a_finding_without_file_line_and_quoted_code_is_dropped(self):
        def sloppy_auditor(job):
            out = offline_agents.run_auditor(job)
            if job["job"] != "audit":
                return out
            real = out["candidate_findings"][0]
            no_code = copy.deepcopy(real)
            no_code["evidence"]["quoted_code"] = ""
            no_line = copy.deepcopy(real)
            del no_line["evidence"]["line"]
            wrong_code = copy.deepcopy(real)
            wrong_code["evidence"]["quoted_code"] = "os.system(cmd)"
            no_evidence = {k: v for k, v in real.items() if k != "evidence"}
            out["candidate_findings"] = [no_code, no_line, real, wrong_code, no_evidence]
            return out
        flow = self.run_flow("case_01_sqli_fstring", {"auditor": sloppy_auditor})
        self.assertEqual([c["finding_id"] for c in flow.state["candidate_findings"]], ["F001"])
        self.assertEqual(len(flow.state["dropped_findings"]), 4)
        self.assertEqual(self.events(flow).count("finding_dropped"), 4)
        self.assertEqual(self.status(flow)["F001"]["status"], "verified_awaiting_approval")
        self.assertEqual(len(flow.state["finding_status"]), 1)        # dropped findings are never counted

    # -------------------------------------------------------------- verified
    def test_a_fix_is_verified_only_if_tests_pass_and_the_recheck_is_clear(self):
        flow = self.run_flow("case_01_sqli_fstring")                     # the real fix: both hold
        self.assertEqual(self.status(flow)["F001"]["status"], "verified_awaiting_approval")
        attempt = flow.state["fix_attempts"][-1]
        self.assertEqual((attempt["tests"]["after"], attempt["recheck"]), ("pass", "clear"))
        # tests pass, but the rule still matches: not verified, retried once, then rejected
        with mock.patch.object(offline_agents, "_sqli_patch", comment_only_patch):
            flow = self.run_flow("case_01_sqli_fstring")
        self.assertEqual(self.status(flow)["F001"]["status"], "rejected")
        self.assertEqual([(a["tests"]["after"], a["recheck"]) for a in flow.state["fix_attempts"]],
                         [("pass", "not_clear")] * 2)
        # an agent that CLAIMS a clean re-check cannot make it so: the Auditor's own re-check decides
        def boastful_fixer(job):
            out = offline_agents.run_fixer_validator(job)
            for attempt in out.get("fix_attempts", []):
                attempt.update(recheck="clear", decision="keep")
            return out
        with mock.patch.object(offline_agents, "_sqli_patch", comment_only_patch):
            flow = self.run_flow("case_01_sqli_fstring", {"fixer_validator": boastful_fixer})
        self.assertEqual(self.status(flow)["F001"]["status"], "rejected")
        self.assertEqual(flow.state["totals"]["fixed_and_verified"] if "totals" in flow.state else 0, 0)

    # -------------------------------------------------------------- loops
    def test_loops_are_bounded_by_retries_caps_and_repeats(self):
        for key, value in {"max_retries": 1, "file_cap": 200, "ai_call_cap": 60, "time_cap_seconds": 1200}.items():
            self.assertEqual(DEFAULT_POLICY[key], value)
        # one retry per finding: a fix whose tests keep failing is tried exactly twice, then rejected
        with mock.patch.object(offline_agents, "_sqli_patch", test_breaking_patch):
            flow = self.run_flow("case_01_sqli_fstring")
        self.assertEqual([a["attempt"] for a in flow.state["fix_attempts"]], [1, 2])
        self.assertEqual(self.status(flow)["F001"]["status"], "rejected")
        self.assertIn("attempt_undone", self.events(flow))                # the copy was restored before the retry
        # ai_call_cap: the audit used the one allowed call, so nothing else starts
        def costly_auditor(job):
            out = offline_agents.run_auditor(job)
            out["usage"]["ai_calls"] = 1
            return out
        flow = self.run_flow("case_01_sqli_fstring", {"auditor": costly_auditor}, {"ai_call_cap": 1})
        self.assertEqual(flow.state["cap_hit"], "ai_calls")
        self.assertEqual(self.status(flow)["F001"]["status"], "not_processed")
        # time_cap: the audit overruns the cap, so no further agent starts and the finding is not_processed
        # (the clock is faked so the test does not depend on how fast this machine is: 0 s until the audit has run, then 5 s)
        audited = {"done": False}

        def slow_auditor(job):
            audited["done"] = True
            return offline_agents.run_auditor(job)
        with mock.patch.object(Workflow, "_elapsed", lambda self: 5.0 if audited["done"] else 0.0):
            flow = self.run_flow("case_01_sqli_fstring", {"auditor": slow_auditor}, {"time_cap_seconds": 1})
        self.assertEqual(flow.state["cap_hit"], "time")
        self.assertEqual(self.status(flow)["F001"]["status"], "not_processed")
        # file_cap: the file list is cut short and the run says so
        flow = self.run_flow("case_05_multifile_sqli", policy={"file_cap": 1})
        self.assertEqual(flow.state["cap_hit"], "files")
        self.assertTrue(flow.state["file_list"]["truncated"])
        # the same agent twice in a row with no new state stops the run
        flow = self.run_flow("case_01_sqli_fstring")
        stuck = {"baseline_tests": {"outcome": "pass", "exit_code": 0}, "usage": dict(USAGE_ZERO)}
        flow.agents["fixer_validator"] = lambda job: copy.deepcopy(stuck)
        flow._last_handoff = None
        flow._handoff("fixer_validator", "baseline_tests", None, {})
        with self.assertRaises(RunStopped):
            flow._handoff("fixer_validator", "baseline_tests", None, {})
        self.assertIn("alert_loop_detected", self.events(flow))

    # -------------------------------------------------------------- hand to a person
    def test_every_hand_to_a_person_trigger_fires_with_the_full_package(self):
        # tests missing (case_08)
        flow = self.run_flow("case_08_no_tests")
        row = self.status(flow)["F001"]
        self.assertEqual((row["status"], row["reason"]), ("needs_a_person",
                         "no tests exist, so a fix cannot be verified"))
        self.assertEqual(self.assert_handoff_package(flow, "F001")["tests"], {"before": "none", "after": None})
        # fix_allowed false (case_06, a dependency)
        flow = self.run_flow("case_06_old_library_version")
        self.assertEqual(self.status(flow)["F001"]["reason"], "fix not allowed")
        self.assertIsNone(self.assert_handoff_package(flow, "F001")["patch_diff"])
        # redesign needed (case_07)
        flow = self.run_flow("case_07_raw_sql_from_client")
        self.assertIn("redesign", self.status(flow)["F001"]["reason"])
        self.assert_handoff_package(flow, "F001")
        # unclear cause: the weak spot is not inside a function the Investigator can trace
        def lost_investigator(job):
            return {"investigations": [{"finding_id": job["finding"]["finding_id"], "traced_cause": None,
                                        "fix_approach": None, "fixable": False,
                                        "handoff_reason": "cause unclear: no path from input to this line"}],
                    "usage": dict(USAGE_ZERO)}
        flow = self.run_flow("case_01_sqli_fstring", {"investigator": lost_investigator})
        self.assertIn("cause unclear", self.status(flow)["F001"]["reason"])
        self.assertIsNone(self.assert_handoff_package(flow, "F001")["traced_cause"])
        # malformed model output
        flow = self.run_flow("case_01_sqli_fstring", {"investigator": lambda job: {"investigations": "yes"}})
        self.assertIn("invalid_output", self.events(flow))
        self.assertEqual(self.status(flow)["F001"]["status"], "needs_a_person")
        self.assert_handoff_package(flow, "F001")
        # retry failed: rejected, with the last patch and the evidence in the package
        with mock.patch.object(offline_agents, "_sqli_patch", comment_only_patch):
            flow = self.run_flow("case_01_sqli_fstring")
        package = self.assert_handoff_package(flow, "F001")
        self.assertEqual((package["status"], package["recheck"], package["tests"]["after"]), ("rejected", "not_clear", "pass"))
        self.assertIn("# reviewed", package["patch_diff"])
        # a cap is hit
        def costly_auditor(job):
            out = offline_agents.run_auditor(job)
            out["usage"]["ai_calls"] = 1
            return out
        flow = self.run_flow("case_01_sqli_fstring", {"auditor": costly_auditor}, {"ai_call_cap": 1})
        self.assertEqual(self.assert_handoff_package(flow, "F001")["status"], "not_processed")
        # AI-only finding below confidence_gate 0.70 (case_11). The offline stand-ins use rule matches only, so the
        # Auditor is wrapped to report it the way a model would; a rule match is never gated.
        def model_auditor(confidence):
            def auditor(job):
                out = offline_agents.run_auditor(job)
                for finding in out.get("candidate_findings", []):
                    finding.update(detected_by="ai_model", confidence=confidence)
                return out
            return auditor
        flow = self.run_flow("case_11_escalate_no_callers", {"auditor": model_auditor(0.55)})
        self.assertIn("low confidence", self.status(flow)["F001"]["reason"])
        self.assertEqual(self.assert_handoff_package(flow, "F001")["confidence"], 0.55)
        self.assertNotIn("investigate", [h["job"] for h in flow.state["handoff_log"]])   # stopped before any work
        flow = self.run_flow("case_11_escalate_no_callers", {"auditor": model_auditor(0.85)})
        self.assertEqual(self.status(flow)["F001"]["status"], "verified_awaiting_approval")   # above the gate

    # -------------------------------------------------------------- policy: fix when the cause is unclear (you decide)
    def test_an_unclear_cause_gets_a_local_fix_for_approval_when_the_policy_is_on(self):
        def lost(job):
            return {"investigations": [{"finding_id": job["finding"]["finding_id"], "traced_cause": None, "fix_approach": None,
                                        "fixable": False, "handoff_reason": "cause unclear: no caller in the project"}],
                    "usage": dict(USAGE_ZERO)}
        flow = self.run_flow("case_01_sqli_fstring", {"investigator": lost}, {"fix_when_cause_unclear": True})
        self.assertEqual(self.status(flow)["F001"]["status"], "verified_awaiting_approval")
        self.assertIn("cause_unclear_fix_proposed", self.events(flow))                 # the model's objection stays in the log
        proposal = self.queue(flow)["proposals"][0]
        self.assertIn("Not traced", proposal["traced_cause"]["explanation"])
        self.assertIn("not traced", proposal["residual_risk"])                         # the person is told what is still unknown
        self.assertEqual(flow.state["approvals"], [])                                  # and nothing is applied without approval
        # the default (policy off) is unchanged: an unclear cause goes to a person
        flow = self.run_flow("case_01_sqli_fstring", {"investigator": lost})
        self.assertEqual(self.status(flow)["F001"]["status"], "needs_a_person")
        # a redesign is never overridden, even with the policy on
        def redesign(job):
            return {"investigations": [{"finding_id": job["finding"]["finding_id"], "traced_cause": None, "fix_approach": None,
                                        "fixable": False, "handoff_reason": "needs a redesign: clients send raw SQL"}],
                    "usage": dict(USAGE_ZERO)}
        flow = self.run_flow("case_01_sqli_fstring", {"investigator": redesign}, {"fix_when_cause_unclear": True})
        self.assertEqual(self.status(flow)["F001"]["status"], "needs_a_person")
        self.assertNotIn("cause_unclear_fix_proposed", self.events(flow))


if __name__ == "__main__":
    unittest.main()
