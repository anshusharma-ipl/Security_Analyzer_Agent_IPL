"""No-AI check of the tools against the golden cases.

For every golden case: list_files, then run_security_rules on every listed file, then
read_code_structure on the listed .py files. Prints one row per case:
    case | rules found (rule, file, line) | expected in expected.json | match
Run from the project folder:  python evals/golden_table.py
expected.json is the answer key: it is never passed to a tool and never edited.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools.list_files import list_files  # noqa: E402
from tools.read_code_structure import read_code_structure  # noqa: E402
from tools.run_security_rules import run_security_rules  # noqa: E402

GOLDEN = os.path.join(ROOT, "golden")
RULES = os.path.join(GOLDEN, "rules.json")


def result(envelope):
    if not envelope["response"]["ok"]:
        raise SystemExit(f"{envelope['tool']} failed: {envelope['response']['error']}")
    return envelope["response"]["result"]


def triple(rule, file, line):
    return f"{rule} {file}:{line}"


def main():
    rows, bad = [], 0
    for name in sorted(n for n in os.listdir(GOLDEN) if n.startswith("case_")):
        root = os.path.join(GOLDEN, name)
        with open(os.path.join(root, "expected.json"), encoding="utf-8") as handle:
            expected = json.load(handle)
        files = [f for f in result(list_files(root, 200))["files"] if f != "expected.json"]
        found = result(run_security_rules(root, RULES, files))["matches"]
        py_files = [f for f in files if f.endswith(".py")]
        structure = result(read_code_structure(root, py_files)) if py_files else {}
        found_set = sorted(triple(m["rule_id"], m["file"], m["line"]) for m in found)
        finding = expected["finding"]
        want = [triple(finding["rule"], finding["file"], finding["line"])] if finding else []
        extra = expected.get("also_reported_not_fixed")  # text such as "SECRET in src/config.py (...)"; no line given
        if extra:
            rule, file = extra.split(" in ", 1)[0], extra.split(" in ", 1)[1].split(" ")[0]
            # expected.json gives no line for this one, so only rule and file are compared
            want.append(f"{rule} {file} (line not stated)")
        compared = [f"{s.split(chr(58))[0]} (line not stated)" if extra and s.startswith(f"{rule} {file}:") else s
                    for s in found_set]
        match = sorted(compared) == sorted(want)
        bad += not match
        rows.append((name, ", ".join(found_set) or "(none)", ", ".join(want) or "(none)", "yes" if match else "NO",
                     len(files), len(structure.get("files", structure)) if structure else 0))
    widths = [max(len(str(r[i])) for r in rows + [("case", "rules found (rule, file:line)", "expected in expected.json",
                                                    "match", "", "")]) for i in range(4)]
    header = ("case", "rules found (rule, file:line)", "expected in expected.json", "match")
    line = " | ".join(h.ljust(w) for h, w in zip(header, widths))
    print(line)
    print("-+-".join("-" * w for w in widths))
    for r in rows:
        print(" | ".join(str(c).ljust(w) for c, w in zip(r[:4], widths)))
    print(f"\n{len(rows) - bad} of {len(rows)} cases match")
    print(f"list_files and read_code_structure ran on all {len(rows)} cases without error")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
