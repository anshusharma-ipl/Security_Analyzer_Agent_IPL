"""Tests for evals/run_evals.py: the answer-key check, the metric arithmetic, and the read-only rule on golden/.

    python -m unittest tests.test_evals -v
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "evals"))

import run_evals  # noqa: E402


def result(case, expected_status="verified_awaiting_approval", findings=(), wanted=(), verified=(), evidence=(0, 0),
           audit=(1, 1), writes=0, rule="SQLI"):
    return {"case": case, "expected": {"expected_status": expected_status, "finding": {"rule": rule}},
            "findings": list(findings), "expected_findings": list(wanted), "verified": list(verified),
            "evidence": {"total": evidence[0], "proven": evidence[1]},
            "audit": {"required": audit[0], "present": audit[1]}, "original_writes": writes}


def finding(rule="SQLI", file="src/a.py", line=2):
    return {"rule_id": rule, "file": file, "line": line}


def wanted(rule="SQLI", file="src/a.py", line=2, severity="high"):
    return {"rule": rule, "file": file, "line": line, "severity": severity}


GOOD = {"applies": True, "tests": "pass", "recheck_clear": True}


class TestExpectedJson(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="saa-evals-test-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.case = os.path.join(self.tmp, "case_x")
        os.makedirs(os.path.join(self.case, "src"))
        with open(os.path.join(self.case, "src", "a.py"), "w", encoding="utf-8") as handle:
            handle.write("a = 1\nb = 2\nc = 3\n")

    def expected(self, **changes):
        base = {"case_id": "case_x", "baseline_tests": "pass", "expected_status": "verified_awaiting_approval",
                "finding": {"rule": "SQLI", "file": "src/a.py", "line": 2}}
        base.update(changes)
        return base

    def test_the_real_answer_keys_are_valid_and_a_bad_one_is_caught(self):
        for name in sorted(n for n in os.listdir(run_evals.GOLDEN) if n.startswith("case_")):
            case = os.path.join(run_evals.GOLDEN, name)
            self.assertEqual(run_evals.validate_expected(case, run_evals._json(os.path.join(case, "expected.json"))), [], name)
        self.assertEqual(run_evals.validate_expected(self.case, self.expected()), [])
        self.assertTrue(run_evals.validate_expected(self.case, self.expected(expected_status="fixed")))      # not in the enum
        self.assertTrue(run_evals.validate_expected(self.case, self.expected(finding={"rule": "SQLI", "file": "src/a.py", "line": 9})))
        self.assertTrue(run_evals.validate_expected(self.case, self.expected(finding={"rule": "SQLI", "file": "src/nope.py", "line": 1})))
        self.assertTrue(run_evals.validate_expected(self.case, self.expected(finding={"rule": "XSS", "file": "src/a.py", "line": 1})))
        self.assertTrue(run_evals.validate_expected(self.case, self.expected(case_id="case_y")))
        self.assertEqual(run_evals.validate_expected(self.case, self.expected(expected_status="safe_nothing_to_report", finding=None)), [])

    def test_golden_is_never_changed_by_a_case_run(self):
        before = run_evals.tree_hash(run_evals.GOLDEN)
        res = run_evals.run_case("case_04_safe_sql_lookalike", self.tmp)
        self.assertTrue(all(c["ok"] for c in res["checks"]), res["checks"])
        self.assertEqual(run_evals.tree_hash(run_evals.GOLDEN), before)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "case_04_safe_sql_lookalike", "project", "expected.json")))
        self.assertTrue(res["run"]["rules_file_version"].startswith("sha256:"))     # recorded in every eval run
        self.assertIn("name", res["run"]["ai_model"])


class TestMetrics(unittest.TestCase):
    def test_the_section_14_numbers_come_out_of_the_case_results(self):
        results = [
            result("c1", findings=[finding()], wanted=[wanted()], verified=[dict(GOOD, rule_id="SQLI", file="src/a.py")],
                   evidence=(1, 1), audit=(10, 10)),
            result("c2", findings=[finding(line=9)], wanted=[wanted()], evidence=(1, 1), audit=(10, 9)),         # wrong line
            result("c3", expected_status="needs_a_person", findings=[finding("PATH", "src/c.py", 3)],
                   wanted=[wanted("PATH", "src/c.py", 3)], verified=[dict(GOOD, rule_id="PATH", file="src/c.py")],
                   evidence=(1, 0), audit=(10, 10)),                                                              # wrong label
            result("c4", expected_status="safe_nothing_to_report", findings=[finding("SECRET", "src/d.py", 1)],
                   wanted=[], evidence=(1, 1), audit=(10, 10), writes=1),
        ]
        m = run_evals.compute_metrics(results)
        self.assertAlmostEqual(m["precision"], 2 / 4)             # c1 and c3 match, c2 (wrong line) and c4 do not
        self.assertAlmostEqual(m["high_recall"], 2 / 3)           # 3 expected high, c1 and c3 found
        self.assertAlmostEqual(m["verified_success"], 1 / 2)      # c1 ok; c2 expected a fix and has none
        self.assertAlmostEqual(m["false_fix"], 1 / 2)             # c3 is verified but should have gone to a person
        self.assertAlmostEqual(m["evidence_coverage"], 3 / 4)
        self.assertAlmostEqual(m["regression_pass"], 1.0)
        self.assertEqual(m["original_writes"], 1)
        self.assertAlmostEqual(m["audit_completeness"], 39 / 40)

    def test_gates_and_the_nothing_to_divide_case(self):
        m = run_evals.compute_metrics([result("c4", expected_status="safe_nothing_to_report")])
        self.assertIsNone(m["precision"])
        self.assertIsNone(m["false_fix"])
        rows = {r["key"]: r["status"] for r in run_evals.gate_rows(m)}
        self.assertEqual(rows["precision"], "not measurable")
        self.assertEqual(rows["original_writes"], "PASS")
        perfect = run_evals.compute_metrics([result("c1", findings=[finding()], wanted=[wanted()], evidence=(1, 1),
                                                    verified=[dict(GOOD, rule_id="SQLI", file="src/a.py")])])
        self.assertTrue(all(r["status"] == "PASS" for r in run_evals.gate_rows(perfect)))
        broken = dict(GOOD, tests="fail")
        bad = run_evals.compute_metrics([result("c1", findings=[finding()], wanted=[wanted()], evidence=(1, 1),
                                                verified=[dict(broken, rule_id="SQLI", file="src/a.py")])])
        self.assertEqual({r["key"]: r["status"] for r in run_evals.gate_rows(bad)}["regression_pass"], "FAIL")
        self.assertEqual({r["key"]: r["status"] for r in run_evals.gate_rows(bad)}["false_fix"], "FAIL")


if __name__ == "__main__":
    unittest.main()
