"""Model-backed agents, tested against a local mock of the Messages API (no network, no key, no real code).

The mock plays a well-behaved model, and a few badly behaved ones, so these tests prove the HARNESS: forced tool
arguments, masking, the evidence rule, the one-patch rule, the forbidden-patch rule, and that the model's own claims
about tests and re-checks are never trusted.
"""
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agents import model_agents, offline_agents  # noqa: E402
from orchestrator.workflow import Workflow  # noqa: E402
from tools.orchestrator_helpers import hash_originals  # noqa: E402

GOLDEN = os.path.join(ROOT, "golden")
RULES = os.path.join(GOLDEN, "rules.json")


class MockModel:
    """A scripted 'model'. mode: good | invent (names a finding the rules never returned) | evil_patch."""
    mode = "good"
    requests: list = []
    lock = threading.Lock()


def _last_tool_result(messages: list, name_hint: str | None = None) -> dict | None:
    for message in reversed(messages):
        if message["role"] == "user" and isinstance(message["content"], list):
            for block in message["content"]:
                if block.get("type") == "tool_result":
                    try:
                        return json.loads(block["content"])
                    except ValueError:
                        return None
    return None


def _tool_results(messages: list) -> list:
    out = []
    for m in messages:
        if m["role"] == "user" and isinstance(m["content"], list):
            for block in m["content"]:
                if block.get("type") == "tool_result":
                    try:
                        out.append(json.loads(block["content"]))
                    except ValueError:
                        out.append({})
    return out


def _job(messages: list) -> dict:
    text = messages[0]["content"]
    return json.loads(text.split("<job_input>")[1].split("</job_input>")[0])


def script(body: dict) -> dict:
    messages, system = body["messages"], body["system"]
    stage = sum(1 for m in messages if m["role"] == "assistant")
    tu = lambda name, args: {"stop_reason": "tool_use", "content": [{"type": "tool_use", "id": f"t{stage}", "name": name, "input": args}]}  # noqa: E731
    end = lambda obj: {"stop_reason": "end_turn", "content": [{"type": "text", "text": json.dumps(obj)}]}  # noqa: E731
    if "# Auditor" in system:
        if stage == 0:
            return tu("list_files", {})
        if stage == 1:
            files = _last_tool_result(messages)["result"]["files"]
            return tu("run_security_rules", {"files": [f for f in files if f.endswith((".py", "requirements.txt"))]})
        if stage == 2 and "src/config.py" in _tool_results(messages)[0]["result"]["files"]:
            return tu("read_file", {"path": "src/config.py"})            # a file with a secret: the model must only see it masked
        matches = _tool_results(messages)[1]["result"]["matches"]
        found = [{"rule_id": m["rule_id"], "file": m["file"], "line": m["line"], "confidence": 0.8} for m in matches]
        if MockModel.mode == "invent":
            found.append({"rule_id": "SQLI", "file": "src/users.py", "line": 99, "confidence": 0.99})
        return end({"candidate_findings": found, "dropped_findings": [], "notes": []})
    if "# Investigator" in system:
        job = _job(messages)
        if stage == 0:
            return tu("read_file", {"path": job["finding"]["file"]})
        if stage == 1:
            return tu("read_code_structure", {"files": [job["finding"]["file"]]})
        return end({"investigations": [{"finding_id": job["finding"]["finding_id"], "traced_cause": {"explanation": "Input reaches the query.", "path": [job["finding"]["file"]]},
                                        "fix_approach": "Use a ? placeholder.", "fixable": True, "handoff_reason": None}]})
    if "# Fixer" in system:
        job = _job(messages)
        f = job["finding"]
        source = "\n".join(re.sub(r"^\d+: ?", "", ln) for ln in job["file_source_numbered"].split("\n"))
        good = offline_agents._sqli_patch(f["file"], source, f["line"])
        if MockModel.mode == "evil_patch" and stage == 0:
            return tu("apply_patch", {"patch_diff": "--- a/tests/test_users.py\n+++ b/tests/test_users.py\n@@ -1,1 +1,1 @@\n-x\n+y\n"})
        first = 1 if MockModel.mode == "evil_patch" else 0
        if stage == first:
            return tu("apply_patch", {"patch_diff": good})
        if stage == first + 1:
            return tu("run_tests", {"workspace": "/etc", "test_command": "rm -rf /"})   # forced arguments must win
        if stage == first + 2:
            return tu("request_recheck", {"files": [f["file"]]})
        return end({"fix_attempts": [{"decision": "reject", "residual_risk": ""}]})        # a wrong claim on purpose
    return end({})


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        with MockModel.lock:
            MockModel.requests.append(body)
        if self.headers.get("x-api-key") != "sk-test-key-123456":
            payload, code = {"error": {"message": "invalid x-api-key sk-test-key-123456"}}, 401
        elif "Reply with the word OK." in json.dumps(body):
            payload, code = {"model": body["model"], "content": [{"type": "text", "text": "OK"}], "usage": {"input_tokens": 8, "output_tokens": 2}}, 200
        else:
            payload, code = {**script(body), "model": body["model"], "usage": {"input_tokens": 100, "output_tokens": 20}}, 200
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


class ModelAgentsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.cfg = model_agents.ModelConfig(f"http://127.0.0.1:{cls.httpd.server_address[1]}", "mock-model", "sk-test-key-123456")
        cls.tmp = tempfile.mkdtemp(prefix="saa-model-test-")
        cls.golden_hash = hash_originals(GOLDEN)

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def setUp(self):
        MockModel.mode, MockModel.requests = "good", []

    def run_case(self, name, use=None):
        src = shutil.copytree(os.path.join(GOLDEN, name), os.path.join(self.tmp, f"s_{name}_{len(os.listdir(self.tmp))}"),
                              ignore=shutil.ignore_patterns("expected.json", "__pycache__"))
        flow = Workflow(agents=model_agents.make_agents(self.cfg, use), out_root=os.path.join(self.tmp, f"o_{name}_{len(os.listdir(self.tmp))}"),
                        ai_model=self.cfg.record())
        flow.start(src, RULES)
        return flow

    def statuses(self, flow):
        return {r["finding_id"]: r["status"] for r in flow.state["finding_status"]}

    def test_connection_ok_and_a_bad_key_is_redacted(self):
        self.assertTrue(model_agents.test_connection(self.cfg)["ok"])
        bad = model_agents.test_connection(model_agents.ModelConfig(self.cfg.endpoint, "m", "sk-test-key-123456x"))
        self.assertFalse(bad["ok"])
        wrong = model_agents.ModelConfig(self.cfg.endpoint, "m", "sk-other-key-999")
        reply = model_agents.test_connection(wrong)
        self.assertNotIn("sk-other-key-999", json.dumps(reply))

    def test_good_model_reaches_a_verified_fix_and_usage_is_counted(self):
        flow = self.run_case("case_01_sqli_fstring")
        self.assertEqual(flow.meta["phase"], "waiting_for_review")
        self.assertEqual(self.statuses(flow), {"F001": "verified_awaiting_approval"})
        c = flow.state["counters"]
        self.assertGreaterEqual(c["ai_calls"], 7)               # audit 3, investigate 3, fix 4 (the recheck and baseline use no model)
        self.assertGreater(c["tokens"]["input"], 0)
        self.assertEqual(flow.state["ai_model"]["name"], "mock-model")
        self.assertNotIn("sk-test-key", json.dumps(flow.state))
        fix = flow.state["fix_attempts"][0]
        self.assertEqual((fix["tests"]["after"], fix["recheck"], fix["decision"]), ("pass", "clear", "keep"))   # the model said reject; the results say keep
        events = [e["event"] for e in flow.state["audit_log"]]
        self.assertIn("decision_overridden", events)

    def test_the_model_cannot_choose_the_folder_or_the_test_command(self):
        flow = self.run_case("case_01_sqli_fstring")
        self.assertEqual(flow.state["baseline_tests"]["outcome"], "pass")
        self.assertEqual(self.statuses(flow), {"F001": "verified_awaiting_approval"})   # run_tests(/etc, rm -rf /) was overridden
        for req in MockModel.requests:
            self.assertNotIn("workspace", json.dumps(req["tools"]))
            self.assertNotIn("test_command", json.dumps(req["tools"]))

    def test_a_finding_the_rules_never_returned_is_dropped(self):
        MockModel.mode = "invent"
        flow = self.run_case("case_01_sqli_fstring")
        self.assertEqual([f["line"] for f in flow.state["candidate_findings"]], [2])
        self.assertTrue(any(d["line"] == 99 for d in flow.state["dropped_findings"]))
        self.assertIn("unbacked_finding_dropped", [e["event"] for e in flow.state["audit_log"]])

    def test_a_patch_that_edits_the_tests_is_refused(self):
        MockModel.mode = "evil_patch"
        flow = self.run_case("case_01_sqli_fstring")
        self.assertIn("model_patch_refused", [e["event"] for e in flow.state["audit_log"]])
        self.assertEqual(self.statuses(flow), {"F001": "verified_awaiting_approval"})   # the honest second patch is accepted
        self.assertNotIn("tests/", flow.state["fix_attempts"][0]["patch_diff"])

    def test_secrets_never_reach_the_model(self):
        flow = self.run_case("case_10_secret_and_personal_data")
        blob = json.dumps(MockModel.requests)
        for value in ("FAKE-KEY-0000-NOT-A-REAL-SECRET", "asha@example.test", "+91-90000-00001"):
            self.assertNotIn(value, blob)
        self.assertGreater(flow.state["sensitive_items_hidden"], 0)

    def test_no_tests_means_no_fix_call(self):
        flow = self.run_case("case_08_no_tests")
        self.assertEqual(self.statuses(flow), {"F001": "needs_a_person"})
        self.assertFalse(any("# Fixer" in r["system"] for r in MockModel.requests))

    def test_one_agent_can_stay_offline(self):
        flow = self.run_case("case_01_sqli_fstring", use={"auditor": False, "investigator": True, "fixer_validator": True})
        self.assertFalse(any("# Auditor" in r["system"] for r in MockModel.requests))
        self.assertEqual(self.statuses(flow), {"F001": "verified_awaiting_approval"})

    def test_golden_is_unchanged(self):
        self.assertEqual(hash_originals(GOLDEN), self.golden_hash)



class ConsoleModelTest(unittest.TestCase):
    """The console's Model panel: connect, test, choose agents, run; the key is never shown again."""

    @classmethod
    def setUpClass(cls):
        from http.server import ThreadingHTTPServer
        from ui import server
        cls.server = server
        cls.mock = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.mock.serve_forever, daemon=True).start()
        cls.mock_url = f"http://127.0.0.1:{cls.mock.server_address[1]}"
        cls.tmp = tempfile.mkdtemp(prefix="saa-ui-model-")
        server.DATA = cls.tmp
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.mock.shutdown()
        cls.server.MODEL.update(cfg=None, source=None)

    def call(self, path, data=None):
        import urllib.error
        import urllib.request
        req = urllib.request.Request(self.base + path, data=json.dumps(data).encode() if data is not None else None,
                                     headers={"Content-Type": "application/json"} if data is not None else {})
        try:
            with urllib.request.urlopen(req) as r:
                return r.status, json.loads(r.read())
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def test_connect_test_run_and_the_key_stays_hidden(self):
        MockModel.mode, MockModel.requests = "good", []
        s, m = self.call("/api/model", {"endpoint": self.mock_url, "model": "mock-model", "api_key": "sk-test-key-123456"})
        self.assertEqual(s, 200)
        self.assertTrue(m["configured"])
        self.assertNotIn("sk-test-key-123456", json.dumps(m))
        self.assertNotIn("sk-test-key-123456", json.dumps(self.call("/api/info")[1]))
        self.assertTrue(self.call("/api/model/test", {})[1]["ok"])
        # an agent is ticked but the acknowledgement is missing -> refused
        s, r = self.call("/api/jobs", {"case": "case_01_sqli_fstring", "use_model": {"fixer_validator": True}})
        self.assertEqual(s, 400)
        self.assertIn("confirm", r["error"])
        s, r = self.call("/api/jobs", {"case": "case_01_sqli_fstring", "model_ack": True,
                                       "use_model": {"auditor": True, "investigator": True, "fixer_validator": True}})
        self.assertEqual(s, 200)
        for _ in range(300):
            v = self.call("/api/jobs/" + r["job_id"])[1]
            if v["phase"] in ("waiting_for_review", "done", "stopped", "error"):
                break
            time.sleep(0.2)
        self.assertEqual(v["phase"], "waiting_for_review")
        self.assertEqual(v["model_used"], ["auditor", "investigator", "fixer_validator"])
        self.assertEqual(v["state"]["ai_model"]["name"], "mock-model")
        self.assertGreater(v["state"]["counters"]["ai_calls"], 0)
        self.assertNotIn("sk-test-key-123456", json.dumps(v))
        # disconnect -> using the model is refused
        self.call("/api/model/clear", {})
        s, r = self.call("/api/jobs", {"case": "case_01_sqli_fstring", "model_ack": True, "use_model": {"auditor": True}})
        self.assertEqual(s, 400)
        self.assertEqual(self.call("/api/model")[1]["configured"], False)


if __name__ == "__main__":
    unittest.main()
