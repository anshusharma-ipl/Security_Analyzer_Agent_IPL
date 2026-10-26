"""Tests for the seven agent tools, the orchestrator helpers and the CLI.

Run from the project folder:   python -m unittest discover -s tests -v

Fixture projects are built in temp folders. The golden cases are only ever READ or copied;
hash_originals / verify_originals prove the golden folder is unchanged after the tests run.
Links: a real symlink needs a privilege on Windows, so the tests fall back to an NTFS
junction (no privilege needed). If neither can be made the link tests are skipped, loudly.
"""
import ast
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools import _schema  # noqa: E402
from tools._safety import SafetyError, resolve_inside  # noqa: E402
from tools.apply_patch import apply_patch  # noqa: E402
from tools.list_files import list_files  # noqa: E402
from tools.orchestrator_helpers import hash_originals, make_temp_copy, verify_originals  # noqa: E402
from tools.read_code_structure import read_code_structure  # noqa: E402
from tools.read_file import read_file  # noqa: E402
from tools.request_recheck import request_recheck  # noqa: E402
from tools.run_security_rules import run_security_rules  # noqa: E402
from tools.run_tests import run_tests  # noqa: E402

GOLDEN = os.path.join(ROOT, "golden")
RULES = os.path.join(GOLDEN, "rules.json")
CASE_01 = os.path.join(GOLDEN, "case_01_sqli_fstring")
UNITTEST_CMD = "python -m unittest discover -s tests"

FIX_USERS = """--- a/src/users.py
+++ b/src/users.py
@@ -1,3 +1,3 @@
 def find_user(conn, name):
-    query = f"SELECT id, name FROM users WHERE name = '{name}'"
-    return conn.execute(query).fetchone()
+    query = "SELECT id, name FROM users WHERE name = ?"
+    return conn.execute(query, (name,)).fetchone()
"""


def response(envelope):
    return envelope["response"]


def make_dir_link(link, target):
    """A symlink if allowed, else an NTFS junction. Returns which one. Skips if neither works."""
    try:
        os.symlink(target, link, target_is_directory=True)
        return "symlink"
    except (OSError, NotImplementedError):
        pass
    if os.name == "nt":
        done = subprocess.run(["cmd", "/c", "mklink", "/J", link, target], capture_output=True)
        if done.returncode == 0:
            return "junction"
    raise unittest.SkipTest("this machine cannot create a symlink or a junction")


class Base(unittest.TestCase):
    def temp(self):
        folder = tempfile.mkdtemp(prefix="saa-test-")
        self.addCleanup(shutil.rmtree, folder, True)
        return os.path.realpath(folder)

    def project(self, files, name="proj"):
        root = os.path.join(self.temp(), name)
        for rel, text in files.items():
            path = os.path.join(root, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(text)
        os.makedirs(root, exist_ok=True)
        return root

    def copy_of(self, original, rules=RULES):
        info = make_temp_copy(original, rules)
        self.addCleanup(shutil.rmtree, info["run_dir"], True)
        return info["workspace"]

    def link_to_outside(self, project, secret_name="leak.py", secret_text="TOP_SECRET_OUTSIDE = 1\n"):
        """Make <project>/linkdir pointing at a folder OUTSIDE the project."""
        outside = os.path.join(self.temp(), "outside")
        os.makedirs(outside)
        with open(os.path.join(outside, secret_name), "w", encoding="utf-8") as handle:
            handle.write(secret_text)
        link = os.path.join(project, "linkdir")
        kind = make_dir_link(link, outside)
        self.addCleanup(lambda: os.path.isdir(link) and os.rmdir(link))
        return outside, kind

    def assert_error(self, envelope, code):
        self.assertFalse(response(envelope)["ok"], envelope)
        self.assertEqual(response(envelope)["error"]["code"], code, response(envelope)["error"]["message"])

    def assert_golden_unchanged(self, baseline):
        self.assertEqual(verify_originals(CASE_01, baseline)["unchanged"], True)


# --------------------------------------------------------------------------- list_files
class TestListFiles(Base):
    def test_lists_files_and_skips_the_four_folders(self):
        root = self.project({"a.py": "x = 1\n", "src/b.py": "y = 2\n", ".git/config": "c", "node_modules/m/i.js": "j",
                             ".venv/lib/x.py": "v", "src/__pycache__/b.pyc": "p"})
        result = response(list_files(root, 100))["result"]
        self.assertEqual(result["files"], ["a.py", "src/b.py"])
        self.assertEqual(result["skipped_dirs"], [".git", ".venv", "node_modules", "src/__pycache__"])
        self.assertFalse(result["truncated"])

    def test_stops_at_file_cap_and_says_so(self):
        root = self.project({f"f{i}.py": "" for i in range(5)})
        result = response(list_files(root, 3))["result"]
        self.assertEqual(len(result["files"]), 3)
        self.assertTrue(result["truncated"])

    def test_exactly_at_the_cap_is_not_truncated(self):
        root = self.project({f"f{i}.py": "" for i in range(3)})
        self.assertFalse(response(list_files(root, 3))["result"]["truncated"])

    def test_missing_folder_stops_with_a_clear_message(self):
        envelope = list_files(os.path.join(self.temp(), "nope"), 10)
        self.assert_error(envelope, "folder_not_found")
        self.assertEqual(response(envelope)["error"]["handling"], "stop_run")
        self.assertIn("does not exist", response(envelope)["error"]["message"])

    def test_link_that_leaves_the_project_is_not_followed(self):
        root = self.project({"a.py": "x = 1\n"})
        _outside, _kind = self.link_to_outside(root)
        result = response(list_files(root, 100))["result"]
        self.assertEqual(result["files"], ["a.py"])
        self.assertIn("linkdir", result["skipped_dirs"])

    def test_bad_arguments_are_refused_by_the_schema(self):
        with self.assertRaises(_schema.SchemaError):
            list_files(CASE_01, 0)


# --------------------------------------------------------------------------- read_file
class TestReadFile(Base):
    def test_reads_one_file(self):
        root = self.project({"src/a.py": "one\ntwo\n"})
        result = response(read_file(root, "src/a.py"))["result"]
        self.assertEqual((result["content"], result["line_count"]), ("one\ntwo\n", 2))

    def test_secrets_emails_and_phones_are_hidden_and_lines_keep_their_numbers(self):
        text = "x = 1\nAPI_KEY = \"abcd1234efgh5678\"\n# bob@example.test +91-90000-00001\ny = 2\n"
        result = response(read_file(self.project({"c.py": text}), "c.py"))["result"]
        for real in ("abcd1234efgh5678", "bob@example.test", "90000-00001"):
            self.assertNotIn(real, result["content"])
        self.assertEqual(result["content"].splitlines()[1], "API_KEY = \"<SECRET_1>\"")
        self.assertEqual((result["line_count"], result["sensitive_items_hidden"]), (4, 3))

    def test_path_must_resolve_inside_the_project(self):
        root = self.project({"a.py": "x\n"})
        outside = os.path.join(os.path.dirname(root), "outside.txt")
        with open(outside, "w") as handle:
            handle.write("OUTSIDE")
        for bad in ("../outside.txt", "src/../../outside.txt", outside, "/etc/passwd", "C:\\Windows\\win.ini"):
            with self.subTest(path=bad):
                # Layer 1: the schema refuses the call before any file is touched.
                with self.assertRaises(_schema.SchemaError) as refused:
                    read_file(root, bad)
                self.assertNotIn("OUTSIDE", str(refused.exception))
                # Layer 2: the realpath check refuses it even if the schema were bypassed.
                with self.assertRaises(SafetyError):
                    resolve_inside(root, bad)

    def test_a_link_that_leaves_the_project_is_refused(self):
        root = self.project({"a.py": "x\n"})
        self.link_to_outside(root)
        envelope = read_file(root, "linkdir/leak.py")
        self.assert_error(envelope, "outside_project")
        self.assertIn("leaves the project", response(envelope)["error"]["message"])
        self.assertNotIn("TOP_SECRET_OUTSIDE", json.dumps(envelope))

    def test_missing_and_binary_files_are_skipped_with_a_reason(self):
        root = self.project({"a.py": "x\n"})
        with open(os.path.join(root, "b.bin"), "wb") as handle:
            handle.write(b"\x00\x01\x02")
        self.assert_error(read_file(root, "nope.py"), "file_not_found")
        self.assert_error(read_file(root, "b.bin"), "not_text_file")
        self.assertEqual(response(read_file(root, "nope.py"))["error"]["handling"], "skip_file_and_note")


# --------------------------------------------------------------------------- run_security_rules
class TestRunSecurityRules(Base):
    def found(self, root, files):
        result = response(run_security_rules(root, RULES, files))["result"]
        return {(m["rule_id"], m["file"], m["line"]) for m in result["matches"]}, result

    def test_all_six_rules_find_their_pattern_and_leave_safe_code_alone(self):
        root = self.project({
            "sqli.py": ("def a(c, n):\n    q = f\"SELECT * FROM t WHERE n = '{n}'\"\n    return c.execute(q)\n"
                        "def b(c, n):\n    return c.execute(\"SELECT * FROM t WHERE n = '\" + n + \"'\")\n"
                        "def c2(c, n):\n    return c.execute(\"SELECT * FROM t WHERE n = '%s'\" % n)\n"),
            "cmdi.py": ("import os, subprocess\n"
                        "def a(h):\n    os.system(f\"ping {h}\")\n"
                        "def b(h):\n    subprocess.run('ping ' + h, shell=True)\n"),
            "path.py": ("import os\ndef a(base, name):\n    return open(os.path.join(base, name)).read()\n"),
            "secret.py": "API_KEY = \"abcd1234efgh5678\"\n",
            "weak.py": "import hashlib\ndef h(p):\n    return hashlib.md5(p.encode()).hexdigest()\n",
            "requirements.txt": "requests==2.19.0\nflask==3.0.0\n",
            "safe.py": ("import os, logging\nlog = logging.getLogger('x')\n"
                        "def a(c, n):\n    log.info(f\"SELECT-style report for {n}\")\n"
                        "    return c.execute(\"SELECT * FROM t WHERE n = ?\", (n,))\n"
                        "def b(base, name):\n    p = os.path.realpath(os.path.join(base, name))\n"
                        "    if not p.startswith(os.path.realpath(base)):\n        raise ValueError\n    return p\n"
                        "def c(h):\n    os.system('echo hello')\n"),
        })
        files = ["sqli.py", "cmdi.py", "path.py", "secret.py", "weak.py", "requirements.txt", "safe.py"]
        found, _ = self.found(root, files)
        self.assertEqual(found, {
            ("SQLI", "sqli.py", 2), ("SQLI", "sqli.py", 5), ("SQLI", "sqli.py", 7),
            ("CMDI", "cmdi.py", 3), ("CMDI", "cmdi.py", 5),
            ("PATH", "path.py", 3), ("SECRET", "secret.py", 1), ("WEAKHASH", "weak.py", 3),
            ("DEP-PIN", "requirements.txt", 1)})

    def test_path_rule_needs_a_non_literal_part_after_the_first(self):
        root = self.project({
            "fixed.py": "import os\ndef a(folder):\n    return os.path.join(folder, \"a.txt\")\n",
            "named.py": "import os\ndef a(folder, name):\n    return os.path.join(folder, \"sub\", name)\n",
            "guarded.py": "import os\ndef a(folder, name):\n    return os.path.realpath(os.path.join(folder, name))\n",
        })
        found, _ = self.found(root, ["fixed.py", "named.py", "guarded.py"])
        self.assertEqual(found, {("PATH", "named.py", 3)})

    def test_every_golden_case_gives_exactly_the_expected_findings(self):
        for name in sorted(os.listdir(GOLDEN)):
            case = os.path.join(GOLDEN, name)
            # case_12 and above are red-team inputs (evals/redteam.py): several are MEANT to make the rules wrong
            # (case_15 reports a second finding, case_19 reports a false positive) until the proposed fixes are applied.
            if not name.startswith("case_") or int(name[5:7]) > 11:
                continue
            with self.subTest(case=name):
                with open(os.path.join(case, "expected.json"), encoding="utf-8") as handle:
                    expected = json.load(handle)
                files = [f for f in response(list_files(case, 200))["result"]["files"]
                         if not f.startswith("tests/") and f != "expected.json"]
                found, _ = self.found(case, files)
                want = set()
                if expected["finding"]:
                    want.add((expected["finding"]["rule"], expected["finding"]["file"], expected["finding"]["line"]))
                if "also_reported_not_fixed" in expected:
                    want.add(("SECRET", "src/config.py", 1))
                self.assertEqual(found, want)

    def test_secrets_emails_and_phones_are_hidden_in_quoted_code(self):
        root = self.project({"c.py": "API_KEY = \"abcd1234efgh5678\"  # bob@example.test +91-90000-00001\n"})
        _, result = self.found(root, ["c.py"])
        quoted = result["matches"][0]["quoted_code"]
        for real in ("abcd1234efgh5678", "bob@example.test", "90000-00001"):
            self.assertNotIn(real, quoted)
        self.assertEqual(quoted, "API_KEY = \"<SECRET_1>\"  # <EMAIL_1> <PHONE_1>")
        self.assertEqual(result["sensitive_items_hidden"], 3)

    def test_a_faulty_rule_is_skipped_and_noted_and_the_others_still_run(self):
        root = self.project({"cmdi.py": "import os\nos.system(f'ping {h}')\n"})
        rules = os.path.join(self.temp(), "rules.json")
        with open(rules, "w", encoding="utf-8") as handle:
            json.dump({"rules": [{"id": "NOPE", "severity": "low", "fix_allowed": False, "detect": "x"},
                                 {"id": "CMDI", "severity": "high", "fix_allowed": True, "detect": "x"}]}, handle)
        result = response(run_security_rules(root, rules, ["cmdi.py"]))["result"]
        self.assertEqual([m["rule_id"] for m in result["matches"]], ["CMDI"])
        self.assertEqual(result["skipped_rules"][0]["rule_id"], "NOPE")

    def test_a_bad_rules_file_and_a_link_out_of_the_project_are_refused(self):
        root = self.project({"a.py": "x = 1\n"})
        bad = os.path.join(self.temp(), "bad.json")
        with open(bad, "w", encoding="utf-8") as handle:
            handle.write("{\"rules\": []}")
        self.assert_error(run_security_rules(root, bad, ["a.py"]), "rules_file_unreadable")
        self.link_to_outside(root, "leak.py", "import os\nos.system(f'x {a}')\n")
        result = response(run_security_rules(root, RULES, ["linkdir/leak.py"]))["result"]
        self.assertEqual(result["matches"], [])
        self.assertIn("leaves the project", result["skipped_files"][0]["reason"])

    def test_the_tool_has_no_ai_or_network_code(self):
        source = open(os.path.join(ROOT, "tools", "run_security_rules.py"), encoding="utf-8").read()
        imported = {n.names[0].name.split(".")[0] for n in ast.walk(ast.parse(source)) if isinstance(n, ast.Import)}
        imported |= {n.module.split(".")[0] for n in ast.walk(ast.parse(source))
                     if isinstance(n, ast.ImportFrom) and n.module and not n.level}
        self.assertEqual(imported - {"__future__", "ast", "json", "os", "re", "pathlib"}, set())


# --------------------------------------------------------------------------- read_code_structure
class TestReadCodeStructure(Base):
    def test_functions_calls_and_callers_across_files(self):
        case = os.path.join(GOLDEN, "case_05_multifile_sqli")
        result = response(read_code_structure(case, ["src/views.py", "src/service.py", "src/db.py"]))["result"]
        by_name = {f["name"]: f for f in result["functions"]}
        self.assertEqual({f["file"] for f in result["functions"]}, {"src/views.py", "src/service.py", "src/db.py"})
        self.assertIn("search_users", [c["name"] for c in by_name["handle_search"]["calls"]])
        self.assertEqual([(c["file"], c["function"]) for c in by_name["search_users"]["callers"]],
                         [("src/views.py", "handle_search")])
        self.assertEqual([(c["file"], c["function"]) for c in by_name["run"]["callers"]],
                         [("src/service.py", "search_users")])
        self.assertEqual(by_name["handle_search"]["callers"], [])

    def test_a_function_nobody_calls_has_no_callers(self):
        case = os.path.join(GOLDEN, "case_11_escalate_no_callers")
        result = response(read_code_structure(case, ["src/helpers.py"]))["result"]
        self.assertEqual(result["functions"][0]["callers"], [])

    def test_a_file_that_does_not_parse_is_reported_and_the_rest_is_still_read(self):
        root = self.project({"good.py": "def f():\n    return 1\n", "bad.py": "def (:\n"})
        result = response(read_code_structure(root, ["good.py", "bad.py"]))["result"]
        self.assertEqual([f["name"] for f in result["functions"]], ["f"])
        self.assertEqual(result["unparsed_files"][0]["file"], "bad.py")

    def test_a_path_that_leaves_the_project_is_refused_and_a_missing_file_hands_to_a_person(self):
        root = self.project({"a.py": "def f():\n    pass\n"})
        with self.assertRaises(_schema.SchemaError):
            read_code_structure(root, ["../x.py"])
        self.link_to_outside(root)
        envelope = read_code_structure(root, ["linkdir/leak.py"])
        self.assert_error(envelope, "outside_project")
        self.assertEqual(response(envelope)["error"]["handling"], "hand_to_person")
        self.assert_error(read_code_structure(root, ["missing.py"]), "file_not_found")


# --------------------------------------------------------------------------- apply_patch
class TestApplyPatch(Base):
    def test_patches_the_temporary_copy_and_leaves_the_original_alone(self):
        baseline = hash_originals(CASE_01)
        workspace = self.copy_of(CASE_01)
        result = response(apply_patch(workspace, FIX_USERS))["result"]
        self.assertEqual((result["applied"], result["files_changed"], result["syntax_valid"]),
                         (True, ["src/users.py"], True))
        patched = open(os.path.join(workspace, "src", "users.py"), encoding="utf-8").read()
        self.assertIn("(name,)", patched)
        self.assert_golden_unchanged(baseline)

    def test_a_write_to_the_original_folder_is_refused(self):
        baseline = hash_originals(CASE_01)
        before = open(os.path.join(CASE_01, "src", "users.py"), "rb").read()
        envelope = apply_patch(CASE_01, FIX_USERS)
        self.assert_error(envelope, "outside_workspace")
        self.assertIn("never in the original folder", response(envelope)["error"]["message"])
        self.assertTrue(response(envelope)["error"]["change_undone"])
        self.assertEqual(open(os.path.join(CASE_01, "src", "users.py"), "rb").read(), before)
        self.assert_golden_unchanged(baseline)

    def test_a_folder_that_only_claims_to_be_a_copy_is_refused(self):
        root = self.project({"src/users.py": open(os.path.join(CASE_01, "src", "users.py")).read()})
        self.assert_error(apply_patch(root, FIX_USERS), "outside_workspace")

    def test_a_patch_that_breaks_the_syntax_is_undone(self):
        workspace = self.copy_of(CASE_01)
        target = os.path.join(workspace, "src", "users.py")
        before = open(target, "rb").read()
        broken = FIX_USERS.replace("+    query = \"SELECT id, name FROM users WHERE name = ?\"", "+    query = (")
        envelope = apply_patch(workspace, broken)
        self.assert_error(envelope, "syntax_invalid")
        self.assertEqual(open(target, "rb").read(), before)
        self.assertIn("no longer parses", response(envelope)["error"]["message"])

    def test_a_diff_that_does_not_match_changes_nothing(self):
        workspace = self.copy_of(CASE_01)
        target = os.path.join(workspace, "src", "users.py")
        before = open(target, "rb").read()
        self.assert_error(apply_patch(workspace, FIX_USERS.replace("name = '{name}'", "name = 'X'")),
                          "patch_does_not_apply")
        self.assertEqual(open(target, "rb").read(), before)

    def test_files_outside_the_copy_new_files_deletes_and_package_files_are_refused(self):
        workspace = self.copy_of(CASE_01)
        run_dir = os.path.dirname(workspace)
        escape = FIX_USERS.replace("a/src/users.py", "a/../outside.py").replace("b/src/users.py", "b/../outside.py")
        self.assert_error(apply_patch(workspace, escape), "outside_workspace")
        self.assertFalse(os.path.exists(os.path.join(run_dir, "outside.py")))
        new_file = "--- /dev/null\n+++ b/src/new.py\n@@ -0,0 +1 @@\n+x = 1\n"
        delete = "--- a/src/users.py\n+++ /dev/null\n@@ -1,3 +0,0 @@\n-a\n-b\n-c\n"
        package = "--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1 +1 @@\n-requests==2.19.0\n+requests==2.31.0\n"
        for diff, word in ((new_file, "creates a new file"), (delete, "deleting files is never allowed"),
                           (package, "not a .py file")):
            envelope = apply_patch(workspace, diff)
            self.assert_error(envelope, "patch_does_not_apply")
            self.assertIn(word, response(envelope)["error"]["message"])
        self.assertFalse(os.path.exists(os.path.join(workspace, "src", "new.py")))


# --------------------------------------------------------------------------- run_tests
class TestRunTests(Base):
    def test_pass_fail_and_no_tests(self):
        passing = self.copy_of(CASE_01)
        result = response(run_tests(passing, UNITTEST_CMD, 60))["result"]
        self.assertEqual((result["outcome"], result["exit_code"]), ("pass", 0))
        failing = self.project({"tests/test_x.py": "import unittest\nclass T(unittest.TestCase):\n"
                                                    "    def test_x(self):\n        self.assertEqual(1, 2)\n"})
        failing_ws = self.copy_of(failing)
        result = response(run_tests(failing_ws, UNITTEST_CMD, 60))["result"]
        self.assertEqual(result["outcome"], "fail")
        self.assertNotEqual(result["exit_code"], 0)
        no_folder = self.copy_of(os.path.join(GOLDEN, "case_08_no_tests"))
        self.assertEqual(response(run_tests(no_folder, UNITTEST_CMD, 60))["result"]["outcome"], "none")
        empty = self.copy_of(self.project({"tests/readme.txt": "no tests here\n"}))
        self.assertEqual(response(run_tests(empty, UNITTEST_CMD, 60))["result"]["outcome"], "none")

    def test_a_run_in_the_original_folder_is_refused(self):
        baseline = hash_originals(CASE_01)
        envelope = run_tests(CASE_01, UNITTEST_CMD, 60)
        self.assert_error(envelope, "outside_workspace")
        self.assertEqual(response(envelope)["error"]["handling"], "not_verified_tell_person")
        self.assert_golden_unchanged(baseline)

    def test_the_environment_is_scrubbed(self):
        os.environ["SAA_TEST_SECRET"] = "should-not-reach-the-tests"
        self.addCleanup(os.environ.pop, "SAA_TEST_SECRET", None)
        probe = self.project({"tests/test_env.py": (
            "import os, unittest\nclass T(unittest.TestCase):\n    def test_env(self):\n"
            "        self.assertIsNone(os.environ.get('SAA_TEST_SECRET'))\n"
            "        self.assertEqual(os.environ.get('CI'), '1')\n")})
        self.assertEqual(os.environ.get("SAA_TEST_SECRET"), "should-not-reach-the-tests")  # control: it is set here
        result = response(run_tests(self.copy_of(probe), UNITTEST_CMD, 60))["result"]
        self.assertEqual(result["outcome"], "pass", result["output_tail"])

    def test_a_timeout_stops_the_tests(self):
        slow = self.project({"tests/test_slow.py": (
            "import time, unittest\nclass T(unittest.TestCase):\n    def test_slow(self):\n        time.sleep(60)\n")})
        started = time.monotonic()
        envelope = run_tests(self.copy_of(slow), UNITTEST_CMD, 3)
        self.assert_error(envelope, "timeout")
        self.assertLess(time.monotonic() - started, 30)

    def test_output_has_secrets_hidden_and_an_unknown_command_is_an_error(self):
        noisy = self.project({"tests/test_n.py": (
            "import unittest\nclass T(unittest.TestCase):\n    def test_n(self):\n"
            "        print('mail bob@example.test key')\n")})
        tail = response(run_tests(self.copy_of(noisy), "python -m unittest discover -s tests -v", 60))["result"]["output_tail"]
        self.assertNotIn("bob@example.test", tail)
        self.assertIn("<EMAIL_1>", tail)
        self.assert_error(run_tests(self.copy_of(noisy), "no-such-program-xyz --flag", 10), "command_not_found")


# --------------------------------------------------------------------------- request_recheck
class TestRequestRecheck(Base):
    def test_clear_after_the_fix_and_not_clear_before_it(self):
        unfixed = self.copy_of(CASE_01)
        result = response(request_recheck(unfixed, ["src/users.py"]))["result"]
        self.assertFalse(result["clear"])
        self.assertEqual([(m["rule_id"], m["line"]) for m in result["matches"]], [("SQLI", 2)])
        fixed = self.copy_of(CASE_01)
        self.assertTrue(response(apply_patch(fixed, FIX_USERS))["ok"])
        result = response(request_recheck(fixed, ["src/users.py"]))["result"]
        self.assertEqual((result["clear"], result["matches"]), (True, []))

    def test_an_incomplete_recheck_is_never_called_clear(self):
        workspace = self.copy_of(CASE_01)
        envelope = request_recheck(workspace, ["src/does_not_exist.py"])
        self.assert_error(envelope, "auditor_failed")
        self.assertEqual(response(envelope)["error"]["handling"], "not_verified")

    def test_the_original_folder_is_refused(self):
        self.assert_error(request_recheck(CASE_01, ["src/users.py"]), "outside_workspace")


# --------------------------------------------------------------------------- orchestrator helpers
class TestOrchestratorHelpers(Base):
    def test_make_temp_copy_copies_files_skips_junk_and_never_copies_a_link(self):
        root = self.project({"src/a.py": "x = 1\n", ".git/HEAD": "ref", "src/__pycache__/a.pyc": "p"})
        self.link_to_outside(root)
        info = make_temp_copy(root, RULES)
        self.addCleanup(shutil.rmtree, info["run_dir"], True)
        self.assertEqual(sorted(response(list_files(info["workspace"], 100))["result"]["files"]), ["src/a.py"])
        self.assertFalse(os.path.exists(os.path.join(info["workspace"], "linkdir")))
        self.assertEqual(info["skipped_links"], ["linkdir"])
        self.assertTrue(os.path.isfile(os.path.join(info["run_dir"], "workspace.json")))

    def test_make_temp_copy_refuses_a_run_folder_inside_the_project(self):
        root = self.project({"a.py": "x\n"})
        from tools._safety import SafetyError
        with self.assertRaises(SafetyError):
            make_temp_copy(root, RULES, run_dir=os.path.join(root, "run"))

    def test_verify_originals_catches_a_change_an_addition_and_a_removal(self):
        root = self.project({"a.py": "one\n", "b.py": "two\n", "c.py": "three\n"})
        baseline = hash_originals(root)
        self.assertEqual(verify_originals(root, baseline)["unchanged"], True)
        with open(os.path.join(root, "a.py"), "a") as handle:
            handle.write("tampered\n")
        os.remove(os.path.join(root, "b.py"))
        with open(os.path.join(root, "d.py"), "w") as handle:
            handle.write("new\n")
        check = verify_originals(root, baseline)
        self.assertEqual((check["unchanged"], check["changed"], check["removed"], check["added"]),
                         (False, ["a.py"], ["b.py"], ["d.py"]))


# --------------------------------------------------------------------------- command line
class TestCli(Base):
    def run_cli(self, *argv):
        return subprocess.run([sys.executable, "-m", "tools.cli", *argv], cwd=ROOT, capture_output=True, text=True,
                              encoding="utf-8")

    def test_runs_a_tool_and_prints_the_envelope(self):
        done = self.run_cli("list_files", json.dumps({"root": CASE_01, "file_cap": 50}))
        self.assertEqual(done.returncode, 0, done.stderr)
        out = json.loads(done.stdout)
        self.assertEqual((out["tool"], out["response"]["ok"]), ("list_files", True))
        self.assertIn("src/users.py", out["response"]["result"]["files"])

    def test_exit_codes_for_a_tool_error_and_for_a_bad_call(self):
        done = self.run_cli("read_file", json.dumps({"root": CASE_01, "path": "src/missing.py"}))
        self.assertEqual(done.returncode, 1)
        self.assertEqual(json.loads(done.stdout)["response"]["error"]["code"], "file_not_found")
        for argv in (("no_such_tool", "{}"), ("list_files", "not json"), ("list_files", "[]"),
                     ("read_file", json.dumps({"root": CASE_01, "path": "../x"})),
                     ("list_files", json.dumps({"root": CASE_01, "file_cap": 0})),
                     ("list_files", json.dumps({"root": CASE_01})), ("list_files",)):
            self.assertEqual(self.run_cli(*argv).returncode, 2, argv)

    def test_orchestrator_helpers_are_not_reachable_from_the_command_line(self):
        for name in ("make_temp_copy", "hash_originals", "verify_originals"):
            self.assertEqual(self.run_cli(name, json.dumps({"original_root": CASE_01})).returncode, 2)


# --------------------------------------------------------------------------- conventions
class TestConventions(unittest.TestCase):
    def test_tools_use_only_the_standard_library_and_jsonschema(self):
        allowed = set(sys.stdlib_module_names) | {"jsonschema", "referencing"}
        for name in sorted(os.listdir(os.path.join(ROOT, "tools"))):
            if not name.endswith(".py"):
                continue
            tree = ast.parse(open(os.path.join(ROOT, "tools", name), encoding="utf-8").read())
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    modules = [a.name.split(".")[0] for a in node.names]
                elif isinstance(node, ast.ImportFrom) and not node.level and node.module:
                    modules = [node.module.split(".")[0]]
                else:
                    continue
                for module in modules:
                    self.assertIn(module, allowed, f"{name} imports {module}")

    def test_all_seven_tools_have_a_schema(self):
        for tool in ("list_files", "read_file", "run_security_rules", "read_code_structure", "apply_patch",
                     "run_tests", "request_recheck"):
            self.assertTrue(os.path.isfile(os.path.join(ROOT, "schemas", f"tool_{tool}.schema.json")), tool)


if __name__ == "__main__":
    unittest.main()
