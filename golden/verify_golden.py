"""Checks that every golden case behaves as its expected.json says before any fix:
tests pass, fail or are missing. Run: python3 verify_golden.py"""
import json, os, subprocess, sys

HERE = os.path.dirname(os.path.abspath(__file__))
bad = 0
for name in sorted(os.listdir(HERE)):
    case = os.path.join(HERE, name)
    if not name.startswith("case_"):
        continue
    exp = json.load(open(os.path.join(case, "expected.json")))
    if not os.path.isdir(os.path.join(case, "tests")):
        got = "none"
    else:
        r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                           cwd=case, capture_output=True, text=True)
        got = "pass" if r.returncode == 0 else "fail"
    ok = got == exp["baseline_tests"]
    bad += not ok
    print(("OK   " if ok else "FAIL ") + name + "  tests: " + got)
print("all cases as expected" if not bad else str(bad) + " case(s) differ")
sys.exit(1 if bad else 0)
