"""Tests for tools/mcp_server.py (run: python -m unittest tests.test_mcp  or  discover -s tests).

Most tests call handle() in-process (fast). A few start the real server over stdio.
"""
import io
import json
import os
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from tools import mcp_server  # noqa: E402
from tools.cli import TOOLS  # noqa: E402
from tools.orchestrator_helpers import make_temp_copy  # noqa: E402

CASE_01 = os.path.join(ROOT, "golden", "case_01_sqli_fstring")
RULES = os.path.join(ROOT, "golden", "rules.json")
EXPECTED = {
    "auditor": ["list_files", "read_file", "run_security_rules"],
    "investigator": ["read_file", "read_code_structure"],
    "fixer-validator": ["apply_patch", "run_tests", "request_recheck"],
}


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def rpc(agent, method, params=None, request_id=1):
    message = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        message["params"] = params
    return mcp_server.handle(message, agent)


def call(agent, name, arguments):
    return rpc(agent, "tools/call", {"name": name, "arguments": arguments})


class Handshake(unittest.TestCase):
    def test_initialize(self):
        result = rpc("auditor", "initialize", {"protocolVersion": "2025-06-18"})["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertIn("tools", result["capabilities"])

    def test_unknown_version_gets_a_supported_one(self):
        result = rpc("auditor", "initialize", {"protocolVersion": "1999-01-01"})["result"]
        self.assertIn(result["protocolVersion"], mcp_server.SUPPORTED_VERSIONS)

    def test_notification_gets_no_reply(self):
        self.assertIsNone(mcp_server.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, "auditor"))

    def test_unknown_method(self):
        self.assertEqual(rpc("auditor", "resources/list")["error"]["code"], mcp_server.METHOD_NOT_FOUND)

    def test_not_a_request(self):
        for bad in ([], "x", {"id": 1}, {"jsonrpc": "1.0", "id": 1, "method": "tools/list"}):
            self.assertEqual(mcp_server.handle(bad, "auditor")["error"]["code"], mcp_server.INVALID_REQUEST)

    def test_bad_params(self):
        self.assertEqual(rpc("auditor", "tools/call", [])["error"]["code"], mcp_server.INVALID_PARAMS)
        self.assertEqual(rpc("auditor", "tools/call", {})["error"]["code"], mcp_server.INVALID_PARAMS)
        self.assertEqual(rpc("auditor", "tools/call", {"name": "read_file", "arguments": []})["error"]["code"],
                         mcp_server.INVALID_PARAMS)


class Listing(unittest.TestCase):
    def test_each_agent_lists_only_its_tools(self):
        for agent, names in EXPECTED.items():
            tools = rpc(agent, "tools/list")["result"]["tools"]
            self.assertEqual([t["name"] for t in tools], names, agent)

    def test_name_description_and_schema(self):
        for agent in EXPECTED:
            for tool in rpc(agent, "tools/list")["result"]["tools"]:
                self.assertTrue(tool["description"].strip())
                self.assertNotIn("\n", tool["description"])
                schema = tool["inputSchema"]
                self.assertEqual(schema["type"], "object")
                self.assertFalse(schema["additionalProperties"])
                self.assertTrue(schema["required"])
                json.dumps(schema)  # must be plain JSON

    def test_schema_matches_the_schemas_folder(self):
        path = os.path.join(ROOT, "schemas", "tool_read_file.schema.json")
        arguments = json.loads(read_text(path))["properties"]["arguments"]
        tool = rpc("investigator", "tools/list")["result"]["tools"][0]
        self.assertEqual(tool["name"], "read_file")
        self.assertEqual(tool["inputSchema"]["properties"], arguments["properties"])

    def test_refs_resolve(self):
        tool = next(t for t in rpc("auditor", "tools/list")["result"]["tools"] if t["name"] == "run_security_rules")
        self.assertIn("path", tool["inputSchema"]["$defs"])

    def test_only_the_seven_tools_exist(self):
        every = {n for names in EXPECTED.values() for n in names}
        self.assertEqual(every, set(TOOLS))
        self.assertEqual(len(TOOLS), 7)
        for banned in ("shell", "exec", "run_command", "write_file", "delete_file", "make_temp_copy",
                       "hash_originals", "verify_originals"):
            self.assertNotIn(banned, every)


class Calls(unittest.TestCase):
    def setUp(self):
        info = make_temp_copy(CASE_01, RULES)
        self.addCleanup(shutil.rmtree, info["run_dir"], True)
        self.workspace = info["workspace"]

    def payload(self, answer):
        self.assertIn("result", answer, answer)
        return json.loads(answer["result"]["content"][0]["text"])

    def test_auditor_finds_the_sqli(self):
        answer = call("auditor", "run_security_rules",
                      {"root": CASE_01, "rules_file": RULES, "files": ["src/users.py"]})
        self.assertFalse(answer["result"]["isError"])
        matches = self.payload(answer)["result"]["matches"]
        self.assertEqual([(m["rule_id"], m["file"], m["line"]) for m in matches], [("SQLI", "src/users.py", 2)])

    def test_auditor_lists_and_reads(self):
        listed = self.payload(call("auditor", "list_files", {"root": CASE_01, "file_cap": 200}))
        self.assertIn("src/users.py", json.dumps(listed))
        self.assertFalse(call("auditor", "read_file", {"root": CASE_01, "path": "src/users.py"})["result"]["isError"])

    def test_investigator_reads_structure(self):
        answer = call("investigator", "read_code_structure", {"root": CASE_01, "files": ["src/users.py"]})
        self.assertFalse(answer["result"]["isError"])

    def test_fixer_validator_rechecks_the_copy(self):
        answer = call("fixer-validator", "request_recheck", {"workspace": self.workspace, "files": ["src/users.py"]})
        self.assertFalse(answer["result"]["isError"])
        self.assertIn("SQLI", json.dumps(self.payload(answer)))

    def test_every_other_tool_is_refused(self):
        for agent, owned in EXPECTED.items():
            for name in TOOLS:
                if name in owned:
                    continue
                answer = call(agent, name, {})
                self.assertEqual(answer["error"]["code"], mcp_server.INVALID_PARAMS, (agent, name))
                self.assertIn("not available", answer["error"]["message"])

    def test_unknown_tool_is_refused(self):
        for name in ("bash", "write_file", "make_temp_copy", "", None):
            answer = rpc("fixer-validator", "tools/call", {"name": name, "arguments": {}})
            self.assertIn("error", answer, name)

    def test_refused_tool_does_not_run(self):
        # an auditor must not be able to reach apply_patch, even with valid arguments
        before = read_text(os.path.join(self.workspace, "src", "users.py"))
        diff = "--- a/src/users.py\n+++ b/src/users.py\n@@ -1 +1 @@\n-x\n+y\n"
        answer = call("auditor", "apply_patch", {"workspace": self.workspace, "patch_diff": diff})
        self.assertIn("error", answer)
        self.assertEqual(read_text(os.path.join(self.workspace, "src", "users.py")), before)


class Errors(unittest.TestCase):
    def assert_tool_error(self, answer, needle):
        self.assertTrue(answer["result"]["isError"], answer)
        text = answer["result"]["content"][0]["text"]
        self.assertIn(needle, text)
        self.assertNotIn("Traceback", text)
        self.assertNotIn('File "', text)

    def test_missing_argument(self):
        self.assert_tool_error(call("investigator", "read_file", {"root": CASE_01}), "schema")

    def test_extra_argument(self):
        self.assert_tool_error(call("investigator", "read_file", {"root": CASE_01, "path": "src/users.py", "x": 1}),
                               "schema")

    def test_wrong_type(self):
        self.assert_tool_error(call("investigator", "read_file", {"root": 5, "path": "src/users.py"}), "schema")

    def test_path_escape_refused_by_schema(self):
        for path in ("../secret.txt", "/etc/passwd", "C:\\Windows\\win.ini"):
            self.assert_tool_error(call("investigator", "read_file", {"root": CASE_01, "path": path}), "schema")

    def test_tool_error_is_an_error_result(self):
        answer = call("investigator", "read_file", {"root": CASE_01, "path": "src/missing.py"})
        self.assertTrue(answer["result"]["isError"])
        self.assertIn("file_not_found", answer["result"]["content"][0]["text"])

    def test_write_tools_refuse_the_original(self):
        answer = call("fixer-validator", "request_recheck", {"workspace": CASE_01, "files": ["src/users.py"]})
        self.assertTrue(answer["result"]["isError"])
        self.assertIn("outside_workspace", answer["result"]["content"][0]["text"])
        self.assertNotIn("Traceback", answer["result"]["content"][0]["text"])

    def test_unexpected_exception_has_no_traceback(self):
        original = mcp_server.TOOLS["read_file"]
        mcp_server.TOOLS["read_file"] = lambda **kw: 1 / 0
        try:
            self.assert_tool_error(call("investigator", "read_file", {"root": CASE_01, "path": "src/users.py"}),
                                   "ZeroDivisionError")
        finally:
            mcp_server.TOOLS["read_file"] = original


class Stdio(unittest.TestCase):
    def test_serve_in_process(self):
        lines = [
            '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}',
            '{"jsonrpc":"2.0","method":"notifications/initialized"}',
            "not json",
            "",
            '{"jsonrpc":"2.0","id":2,"method":"tools/list"}',
        ]
        out = io.StringIO()
        mcp_server.serve("investigator", io.StringIO("\n".join(lines) + "\n"), out)
        replies = [json.loads(x) for x in out.getvalue().splitlines()]
        self.assertEqual([r["id"] for r in replies], [1, None, 2])
        self.assertEqual(replies[1]["error"]["code"], mcp_server.PARSE_ERROR)
        self.assertEqual(len(replies[2]["result"]["tools"]), 2)

    def test_real_process_and_check_flag(self):
        server = subprocess.run(
            [sys.executable, "-m", "tools.mcp_server", "--agent", "auditor"], cwd=ROOT, capture_output=True,
            text=True, encoding="utf-8", timeout=60,
            input='{"jsonrpc":"2.0","id":1,"method":"tools/list"}\n{broken\n')
        self.assertEqual(server.returncode, 0, server.stderr)
        replies = [json.loads(x) for x in server.stdout.splitlines()]
        self.assertEqual([t["name"] for t in replies[0]["result"]["tools"]], EXPECTED["auditor"])
        self.assertEqual(replies[1]["error"]["code"], mcp_server.PARSE_ERROR)
        self.assertEqual(server.stderr, "")

    def test_agent_flag_is_required_and_checked(self):
        for args in ([], ["--agent", "root"], ["--agent", "auditor", "--check"]):
            done = subprocess.run([sys.executable, "-m", "tools.mcp_server", *args], cwd=ROOT,
                                  capture_output=True, text=True, timeout=60, input="")
            self.assertEqual(done.returncode, 2, args)

    def test_check_flag(self):
        done = subprocess.run([sys.executable, "-m", "tools.mcp_server", "--check"], cwd=ROOT,
                              capture_output=True, text=True, timeout=200)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("check passed", done.stdout)
        self.assertNotIn("FAIL", done.stdout)


class NoRulesInWrapper(unittest.TestCase):
    def test_wrapper_imports_no_helper_or_shell(self):
        source = read_text(os.path.join(ROOT, "tools", "mcp_server.py"))
        for word in ("hash_originals", "verify_originals", "shell=True", "os.system", "eval(", "exec("):
            self.assertNotIn(word, source)
        self.assertEqual(source.count("make_temp_copy"), 2)  # only inside check(): import and one call


if __name__ == "__main__":
    unittest.main()
