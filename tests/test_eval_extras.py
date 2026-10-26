"""Tests for the eval additions: per-agent attribution, the judge's guards, and the consistency check.

    python -m unittest tests.test_eval_extras -v
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "evals"))

import attribution  # noqa: E402
import judge  # noqa: E402
import run_evals  # noqa: E402

AGENT_MODEL = {"name": "claude-sonnet-5-5", "version": "x", "endpoint": "https://agents.example.test"}
NO_AGENT = {"name": "none (offline stand-in, no AI model)", "version": "n/a", "endpoint": "none"}
JUDGE_SET = {"name": "other-model", "version": "1", "endpoint": "https://judge.example.test"}
JUDGE_UNSET = {"name": None, "version": None, "endpoint": None}


def case(expected_status="verified_awaiting_approval", want=("SQLI", "src/a.py", 2), findings=(), checks=()):
    expected = {"expected_status": expected_status, "finding": {"rule": want[0], "file": want[1], "line": want[2]} if want else None}
    return {"case": "case_x", "expected": expected, "findings": list(findings), "checks": list(checks)}


def finding(status="verified_awaiting_approval", reason=None, rule="SQLI", file="src/a.py", line=2):
    return {"rule_id": rule, "file": file, "line": line, "status": status, "reason": reason, "finding_id": "F001"}


def failed(name, detail="x"):
    return {"check": name, "ok": False, "detail": detail}


class TestAttribution(unittest.TestCase):
    def test_a_missed_finding_is_the_auditors(self):
        rows = attribution.attribute(case(findings=[], checks=[failed("rule", "no SQLI"), failed("status", "x")]))
        first = attribution.first_wrong(rows)
        self.assertEqual(first["stage"], attribution.AUDITOR)
        self.assertIn("missed", first["why"])

    def test_an_invented_finding_in_a_safe_case_is_the_auditors(self):
        res = case("safe_nothing_to_report", want=None, findings=[finding()], checks=[failed("no unexpected findings"), failed("status")])
        self.assertEqual(attribution.first_wrong(attribution.attribute(res))["stage"], attribution.AUDITOR)

    def test_a_wrong_fixable_call_is_the_investigators(self):
        # case_11 shape: expected a person, but a fix was made
        res = case("needs_a_person", findings=[finding("verified_awaiting_approval")], checks=[failed("status", "got verified")])
        first = attribution.first_wrong(attribution.attribute(res))
        self.assertEqual(first["stage"], attribution.INVESTIGATOR)
        self.assertIn("fixable", first["why"])

    def test_a_kept_bad_fix_is_the_fixers(self):
        res = case(findings=[finding()], checks=[failed("tests pass after the fix", "tests fail")])
        self.assertEqual(attribution.first_wrong(attribution.attribute(res))["stage"], attribution.FIXER)

    def test_no_fix_written_is_the_fixers_and_fixture_failures_are_not_blamed_on_an_agent(self):
        res = case(findings=[finding("needs_a_person", "the fixer could not write a patch for this finding")],
                   checks=[failed("status", "x")])
        self.assertEqual(attribution.first_wrong(attribution.attribute(res))["stage"], attribution.FIXER)
        res = case(findings=[finding("needs_a_person", "the tests are missing")], checks=[failed("status", "x")])
        self.assertEqual(attribution.first_wrong(attribution.attribute(res))["stage"], attribution.NOT_AN_AGENT)

    def test_the_earliest_stage_is_the_first_to_go_wrong(self):
        res = case(findings=[finding()], checks=[failed("tests pass after the fix"), failed("rule", "missing")])
        self.assertEqual(attribution.first_wrong(attribution.attribute(res))["stage"], attribution.AUDITOR)

    def test_a_passing_case_has_no_failure(self):
        res = case(findings=[finding()], checks=[{"check": "rule", "ok": True, "detail": ""}])
        self.assertIsNone(attribution.first_wrong(attribution.attribute(res)))


class TestJudge(unittest.TestCase):
    def test_the_judge_does_not_run_without_an_approved_model(self):
        verdict = judge.run_judge([{"finding_id": "F001", "question": "root_cause", "quoted_code": "q", "text": "t"}],
                                  AGENT_MODEL, JUDGE_UNSET, ask=lambda q, t: "yes")
        self.assertFalse(verdict["ran"])
        self.assertIn("no judge model is approved", verdict["reason"])
        self.assertEqual(verdict["answers"], [])

    def test_the_judge_must_be_a_different_model_from_the_agents(self):
        same = dict(JUDGE_SET, name=AGENT_MODEL["name"])
        verdict = judge.run_judge([], AGENT_MODEL, same, ask=lambda q, t: "yes")
        self.assertFalse(verdict["ran"])
        self.assertIn("different one", verdict["reason"])

    def test_the_judge_sees_only_text_and_its_answers_are_reported_not_applied(self):
        items = judge.items_from([{"finding_id": "F001", "evidence": {"quoted_code": "q = f'x'", "file": "a", "line": 1},
                                   "traced_cause": {"explanation": "from view", "path": ["a"]}, "patch_diff": "d",
                                   "residual_risk": "risk", "status": "verified_awaiting_approval", "rule_id": "SQLI",
                                   "tests": {"before": "pass", "after": "pass"}, "recheck": "clear"}])
        for item in items:
            self.assertEqual(set(item), {"finding_id", "quoted_code", "question", "text"})
        seen = []
        verdict = judge.run_judge(items, AGENT_MODEL, JUDGE_SET, ask=lambda q, text: seen.append(text) or "No ")
        self.assertTrue(verdict["ran"])
        self.assertEqual(verdict["summary"]["root_cause"]["no"], 1)
        self.assertEqual(verdict["summary"]["residual_risk"]["no"], 1)
        self.assertTrue(all("verified_awaiting_approval" not in t and "clear" != t for t in seen))

    def test_an_unexpected_answer_is_counted_as_invalid(self):
        items = [{"finding_id": "F001", "question": "minimal_patch", "quoted_code": "q", "text": "d"}]
        verdict = judge.run_judge(items, AGENT_MODEL, JUDGE_SET, ask=lambda q, t: "probably, maybe")
        self.assertEqual(verdict["summary"]["minimal_patch"]["invalid"], 1)

    def test_a_secret_in_judge_text_is_masked_before_the_model_sees_it(self):
        items = [{"finding_id": "F001", "question": "root_cause", "quoted_code": "k",
                  "text": 'API_KEY = "FAKE-KEY-0000-NOT-A-REAL-SECRET" and asha@example.test'}]
        seen = []
        judge.run_judge(items, AGENT_MODEL, JUDGE_SET, ask=lambda q, t: seen.append(t) or "yes")
        self.assertNotIn("FAKE-KEY-0000-NOT-A-REAL-SECRET", seen[0])
        self.assertNotIn("asha@example.test", seen[0])

    def test_no_judge_client_means_not_run(self):
        verdict = judge.run_judge([], AGENT_MODEL, JUDGE_SET, ask=None)
        self.assertFalse(verdict["ran"])


class TestConsistency(unittest.TestCase):
    def batch(self, status, passed=True):
        return [{"case": "case_x", "findings": [{"rule_id": "SQLI", "file": "a", "line": 2, "status": status}],
                 "passed": passed}]

    def test_a_status_that_changes_between_runs_is_listed(self):
        flips = run_evals.unstable_cases([self.batch("verified_awaiting_approval"), self.batch("needs_a_person")])
        self.assertEqual([f["case"] for f in flips], ["case_x"])

    def test_identical_runs_have_no_flips(self):
        self.assertEqual(run_evals.unstable_cases([self.batch("rejected"), self.batch("rejected")]), [])

    def test_a_pass_that_becomes_a_fail_is_a_flip_too(self):
        flips = run_evals.unstable_cases([self.batch("rejected", True), self.batch("rejected", False)])
        self.assertEqual(len(flips), 1)


if __name__ == "__main__":
    unittest.main()
