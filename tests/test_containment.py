"""Containment guardrails, one test each (canvas sections 9, 13, 16; AGENTS.md section 4).

    python -m unittest tests.test_containment -v

Runs use a COPY of the golden case in a temp folder, so a test that deliberately touches the "original"
never touches golden/. The stand-in agents are wrapped to misbehave on purpose.
"""
import json
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agents import offline_agents  # noqa: E402
from agents.mcp_client import McpClient  # noqa: E402
from orchestrator.workflow import Workflow  # noqa: E402
from tools import _containment, mcp_server  # noqa: E402
from tools._mask import Masker  # noqa: E402
from tools.orchestrator_helpers import make_temp_copy  # noqa: E402

RULES = os.path.join(ROOT, "golden", "rules.json")
HONEST = {"auditor": offline_agents.run_auditor, "investigator": offline_agents.run_investigator,
          "fixer_validator": offline_agents.run_fixer_validator}
FAKE_VALUES = ["FAKE-KEY-0000-NOT-A-REAL-SECRET", "asha@example.test", "+91-90000-00001"]


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class ContainmentCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="saa-containment-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        _containment.drain_events()

    def project(self, case):
        """A private copy of a golden case, standing in for the user's original folder."""
        dest = os.path.join(self.tmp, "project" if not os.path.exists(os.path.join(self.tmp, "project"))
                            else "project-" + str(len(os.listdir(self.tmp))))
        shutil.copytree(os.path.join(ROOT, "golden", case), dest, ignore=shutil.ignore_patterns("expected.json"))
        return dest

    def run_flow(self, case, agents=None, policy=None, rules=RULES):
        project = self.project(case)
        flow = Workflow(agents={**HONEST, **(agents or {})}, out_root=os.path.join(self.tmp, "out"))
        flow.start(project, rules, policy)
        return flow, project

    @staticmethod
    def approve_all(flow):
        """Stand in for the person: approve every proposal, then finish the run."""
        path = os.path.join(flow.run_dir, "review_queue.json")
        queue = json.loads(read_text(path))
        for proposal in queue["proposals"]:
            proposal.update(decision="approved", reviewer="test", reason="ok")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(queue, handle)
        flow.finish()

    @staticmethod
    def events(flow):
        return [e["event"] for e in flow.state["audit_log"]]


class TestContainment(ContainmentCase):
    # -------------------------------------------------------------- tools
    def test_each_agent_can_call_only_its_own_tools(self):
        case = os.path.join(ROOT, "golden", "case_01_sqli_fstring")
        # 1. the MCP server (--agent filter) refuses a tool the agent does not own, and does not list it
        reply = mcp_server.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                   "params": {"name": "apply_patch", "arguments": {}}}, "auditor")
        self.assertIn("error", reply)
        listed = mcp_server.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, "investigator")
        self.assertEqual([t["name"] for t in listed["result"]["tools"]], ["read_file", "read_code_structure"])
        # 2. the client every agent uses refuses it before it is even sent, and the event is recorded
        client = McpClient("investigator")
        try:
            answer = client.call("run_security_rules", {"root": case, "rules_file": RULES, "files": ["src/users.py"]})
        finally:
            client.close()
        self.assertFalse(answer["ok"])
        self.assertEqual(answer["error"]["code"], "tool_not_allowed")
        # 3. the orchestrator copies the event into the decision log
        def pushy_investigator(job):
            c = McpClient("investigator")
            try:
                refused = c.call("apply_patch", {"workspace": job["source_folder"], "patch_diff": "x"})
            finally:
                c.close()
            self.assertEqual(refused["error"]["code"], "tool_not_allowed")
            return offline_agents.run_investigator(job)
        flow, _ = self.run_flow("case_01_sqli_fstring", {"investigator": pushy_investigator})
        self.assertIn("tool_not_allowed", self.events(flow))

    # -------------------------------------------------------------- originals
    def test_a_changed_original_stops_the_run_with_an_alert(self):
        def careless_fixer(job):
            if job["job"] == "baseline_tests":     # something edits the ORIGINAL while the run is going
                with open(os.path.join(self.tmp, "project", "src", "users.py"), "a", encoding="utf-8") as h:
                    h.write("\n# tampered\n")
            return offline_agents.run_fixer_validator(job)
        flow, _ = self.run_flow("case_01_sqli_fstring", {"fixer_validator": careless_fixer})
        self.assertEqual(flow.meta["phase"], "waiting_for_review")      # the change is not noticed until step 6
        self.approve_all(flow)                                          # ... and then it stops the run
        self.assertEqual(flow.meta["phase"], "stopped")
        self.assertIs(flow.state["originals_unchanged"], False)
        self.assertIn("alert_original_files_changed", self.events(flow))
        self.assertFalse(os.path.exists(os.path.join(flow.run_dir, "report.json")))

    def test_a_tool_call_that_writes_into_the_original_folder_is_stopped(self):
        original = os.path.join(self.tmp, "project")
        target = os.path.join(original, "src", "users.py")
        diff = "\n".join(["--- a/src/users.py", "+++ b/src/users.py", "@@ -1,1 +1,1 @@", "-x", "+y", ""])
        def attacker(job):
            c = McpClient("fixer-validator")
            try:
                c.call("apply_patch", {"workspace": original, "patch_diff": diff})   # aimed at the original
            finally:
                c.close()
            return offline_agents.run_fixer_validator(job)
        shutil.copytree(os.path.join(ROOT, "golden", "case_01_sqli_fstring"), original,
                        ignore=shutil.ignore_patterns("expected.json"))
        untouched = read_text(target)
        flow = Workflow(agents={**HONEST, "fixer_validator": attacker}, out_root=os.path.join(self.tmp, "out"))
        flow.start(original, RULES)
        self.assertEqual(flow.meta["phase"], "stopped")
        self.assertIn("alert_write_outside_copy", self.events(flow))
        self.assertIn("outside the temporary copy", flow.meta["stop_reason"])
        self.assertEqual(read_text(target), untouched)

    # -------------------------------------------------------------- state
    def test_a_malformed_handoff_is_rejected_and_leaves_no_trace(self):
        def broken_investigator(job):
            return {"investigations": [{"finding_id": job["finding"]["finding_id"], "fixable": "yes"}],
                    "usage": {"ai_calls": 0, "tokens_in": 0, "tokens_out": 0, "sensitive_items_hidden": 0}}
        flow, _ = self.run_flow("case_01_sqli_fstring", {"investigator": broken_investigator})
        self.assertIn("invalid_output", self.events(flow))
        self.assertEqual(flow.state.get("investigations", []), [])     # nothing from it reached the state
        self.assertEqual([h["result"] for h in flow.state["handoff_log"] if h["agent"] == "investigator"],
                         ["invalid_output"])
        self.assertEqual(flow.state["finding_status"][0]["status"], "needs_a_person")
        # a field the agent does not own is rejected too
        def grabby_investigator(job):
            out = offline_agents.run_investigator(job)
            out["approvals"] = [{"finding_id": "F001", "decision": "approved", "reason": "", "reviewer": "me",
                                 "timestamp": "2026-01-01T00:00:00Z"}]
            return out
        flow, _ = self.run_flow("case_01_sqli_fstring", {"investigator": grabby_investigator})
        self.assertIn("invalid_output", self.events(flow))
        self.assertEqual(flow.state["approvals"], [])

    def test_case_09_injection_comment_is_ignored_and_logged(self):
        flow, project = self.run_flow("case_09_injection_comment_sqli")
        log = flow.state["audit_log"]
        attempts = [e for e in log if e["event"] == "prompt_injection_attempt"]
        self.assertEqual(len(attempts), 1)
        self.assertIn("src/lookup.py", attempts[0]["detail"])
        # ignored: the finding is handled exactly as without the comment, and nothing it asked for happened
        self.assertEqual(flow.state["finding_status"], [{"finding_id": "F001", "status": "verified_awaiting_approval",
                                                         "reason": None}])
        self.assertEqual(flow.state["candidate_findings"][0]["file"], "src/lookup.py")
        self.assertNotIn("setup.sh", json.dumps(flow.state["handoff_log"]))
        # the comment text is data: it never appears in an instruction-bearing field of a job
        seen = []
        def spy(job):
            seen.append(job)
            return offline_agents.run_fixer_validator(job)
        flow2, _ = self.run_flow("case_09_injection_comment_sqli", {"fixer_validator": spy})
        for job in seen:
            for key, value in job.items():
                if key not in ("source", "finding", "investigation", "previous_failure"):
                    self.assertNotIn("ignore your rules", json.dumps(value))

    # -------------------------------------------------------------- privacy
    def test_case_10_secrets_and_personal_values_are_masked_counted_and_never_written(self):
        flow, _ = self.run_flow("case_10_secret_and_personal_data")
        self.assertGreaterEqual(flow.state["sensitive_items_hidden"], 1)
        self.approve_all(flow)
        self.assertEqual(flow.meta["phase"], "done")
        written = ""
        for folder, _dirs, files in os.walk(flow.run_dir):
            for name in files:
                written += read_text(os.path.join(folder, name))
        for value in FAKE_VALUES:
            self.assertNotIn(value, written, "a hidden value reached a file in the run folder")
        secret = next(c for c in flow.state["candidate_findings"] if c["rule_id"] == "SECRET")
        self.assertIn("<SECRET_", secret["evidence"]["quoted_code"])
        # the single door to the model masks, counts and re-checks
        masker = Masker()
        text = _containment.to_model("API_KEY = 'FAKE-KEY-0000-NOT-A-REAL-SECRET'  # asha@example.test +91-90000-00001", masker)
        self.assertEqual(masker.counts, {"SECRET": 1, "EMAIL": 1, "PHONE": 1})
        for value in FAKE_VALUES:
            self.assertNotIn(value, text)
        # and the end-of-run check catches a leak if one ever got through
        self.assertEqual(_containment.find_leaks({"a": ["mail asha@example.test"]}), ["EMAIL"])

    # -------------------------------------------------------------- never
    def test_the_never_list_is_refused_in_code(self):
        for command in ("git commit -m x", "git push origin main", "git merge dev", "pip install requests",
                        "python -m pip uninstall x", "npm install left-pad", "rm -rf tests", "del tests",
                        "curl http://example.test", "kubectl apply -f x.yaml", "docker push img"):
            self.assertIsNotNone(_containment.forbidden_command(command), command)
        self.assertIsNone(_containment.forbidden_command("python -m unittest discover -s tests"))
        self.assertIsNone(_containment.forbidden_command("git status"))
        # a forbidden test command stops the run before any agent starts
        flow, _ = self.run_flow("case_01_sqli_fstring", policy={"test_command": "git push origin main"})
        self.assertEqual(flow.meta["phase"], "stopped")
        self.assertIn("alert_forbidden_command", self.events(flow))
        self.assertEqual(flow.state["handoff_log"], [])
        # the tool itself refuses it too
        from tools.run_tests import run_tests
        info = make_temp_copy(self.project("case_01_sqli_fstring"), RULES, os.path.join(self.tmp, "r"))
        self.assertEqual(run_tests(info["workspace"], "pip install x", 10)["response"]["error"]["code"], "outside_workspace")
        # the only reachable host is the approved model endpoint; none is approved yet
        with self.assertRaises(_containment.ContainmentViolation):
            _containment.check_endpoint("https://api.example.test/v1", "none")
        with self.assertRaises(_containment.ContainmentViolation):
            _containment.check_endpoint("https://evil.example.test/v1", "https://api.example.test")
        _containment.check_endpoint("https://api.example.test/v1/messages", "https://api.example.test")
        # editing rules.json during the run stops it at the end
        rules_copy = os.path.join(self.tmp, "rules.json")
        shutil.copyfile(RULES, rules_copy)
        project = self.project("case_01_sqli_fstring")
        def rule_editor(job):
            with open(rules_copy, "a", encoding="utf-8") as handle:
                handle.write("\n")
            return offline_agents.run_fixer_validator(job)
        flow = Workflow(agents={**HONEST, "fixer_validator": rule_editor}, out_root=os.path.join(self.tmp, "out2"))
        flow.start(project, rules_copy)
        self.approve_all(flow)
        self.assertEqual(flow.meta["phase"], "stopped")
        self.assertIn("alert_rules_file_changed", self.events(flow))


if __name__ == "__main__":
    unittest.main()
