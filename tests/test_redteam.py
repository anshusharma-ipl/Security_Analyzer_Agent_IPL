"""Tests for the red-team cases and runner (evals/redteam.py).

    python -m unittest tests.test_redteam -v

These tests do NOT assert that the system survives each attack (eight of ten currently break it, on purpose, until the
proposed fixes are applied). They check that the attack set is well formed, that the attribution blames the right
stage, and that the two control cases hold.
"""
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "evals"))

import attribution  # noqa: E402
import redteam  # noqa: E402
import run_evals  # noqa: E402


def case(expected_status, findings, checks, want=("SQLI", "src/a.py", 2)):
    return {"case": "case_x", "findings": findings, "checks": checks,
            "expected": {"expected_status": expected_status, "finding": {"rule": want[0], "file": want[1], "line": want[2]}}}


def failed(name):
    return {"check": name, "ok": False, "detail": ""}


def found(status):
    return {"rule_id": "SQLI", "file": "src/a.py", "line": 2, "status": status, "reason": None}


class TestRedTeamSet(unittest.TestCase):
    def test_there_are_ten_attacks_and_each_has_a_valid_answer_key(self):
        self.assertEqual(len(redteam.ATTACKS), 10)
        for attack in redteam.ATTACKS:
            case_dir = os.path.join(run_evals.GOLDEN, attack["case"])
            expected = run_evals._json(os.path.join(case_dir, "expected.json"))
            self.assertEqual(run_evals.validate_expected(case_dir, expected), [], attack["case"])
            self.assertTrue(attack["breaks"] and attack["fix"], attack["case"])

    def test_adversary_cases_are_left_to_the_red_team_runner(self):
        needing = sorted(a["case"] for a in redteam.ATTACKS if any(f for _l, f in a.get("variants", [])))
        marked = sorted(n for n in os.listdir(run_evals.GOLDEN) if n.startswith("case_")
                        and run_evals._json(os.path.join(run_evals.GOLDEN, n, "expected.json")).get("adversary"))
        self.assertEqual(needing, marked)

    def test_the_old_answer_keys_are_untouched(self):
        # expected.json of case_01 .. case_11 must still say what the canvas set out (spot check on three)
        for name, status in (("case_01_sqli_fstring", "verified_awaiting_approval"),
                             ("case_04_safe_sql_lookalike", "safe_nothing_to_report"),
                             ("case_11_escalate_no_callers", "needs_a_person")):
            self.assertEqual(run_evals._json(os.path.join(run_evals.GOLDEN, name, "expected.json"))["expected_status"], status)


class TestAttributionForRedTeam(unittest.TestCase):
    def first(self, res):
        return attribution.first_wrong(attribution.attribute(res))["stage"]

    def test_a_forbidden_patch_that_was_accepted_is_the_fixers(self):
        res = case("rejected", [found("verified_awaiting_approval")],
                   [failed("status"), failed("patch refused: weaken the project's own test")])
        self.assertEqual(self.first(res), attribution.FIXER)

    def test_a_fix_that_breaks_the_code_is_the_fixers_not_the_investigators(self):
        res = case("needs_a_person", [found("verified_awaiting_approval")],
                   [failed("status"), failed("the patched code still works when it is called (reports.build)")])
        self.assertEqual(self.first(res), attribution.FIXER)

    def test_bad_usage_numbers_are_the_agents(self):
        res = case("needs_a_person", [found("verified_awaiting_approval")], [failed("caps cannot be bought with bad usage numbers")])
        self.assertEqual(self.first(res), attribution.INVESTIGATOR)


class TestControls(unittest.TestCase):
    def test_sql_in_comments_and_docstrings_is_not_reported(self):
        attack = next(a for a in redteam.ATTACKS if a["case"] == "case_18_sql_in_comment")
        work = tempfile.mkdtemp(prefix="saa-redteam-test-")
        self.addCleanup(shutil.rmtree, work, ignore_errors=True)
        results = redteam.run_attack(attack, work)
        self.assertTrue(all(r["passed"] for r in results), [c for r in results for c in r["checks"] if not c["ok"]])

    def test_an_unparseable_patch_is_retried_once_and_rejected(self):
        attack = next(a for a in redteam.ATTACKS if a["case"] == "case_17_unparseable_patch")
        work = tempfile.mkdtemp(prefix="saa-redteam-test-")
        self.addCleanup(shutil.rmtree, work, ignore_errors=True)
        results = redteam.run_attack(attack, work)
        self.assertTrue(all(r["passed"] for r in results), [c for r in results for c in r["checks"] if not c["ok"]])


if __name__ == "__main__":
    unittest.main()
