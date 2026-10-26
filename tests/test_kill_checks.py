"""One test per immediate kill criterion (canvas section 16). Each test deliberately triggers the criterion and passes
only if the run STOPS, the alert is raised (alert_kill_<criterion> in the decision log and alert.json), and no report is
written.

    python -m unittest tests.test_kill_checks -v
    python kill_checks.py --run          # the same tests, as a table: kill criterion | check | test result
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import kill_checks  # noqa: E402
from agents import offline_agents  # noqa: E402
from agents.mcp_client import McpClient  # noqa: E402
from orchestrator import workflow as workflow_module  # noqa: E402
from orchestrator.workflow import Workflow  # noqa: E402
from tools import _containment  # noqa: E402

RULES = os.path.join(ROOT, "golden", "rules.json")
HONEST = {"auditor": offline_agents.run_auditor, "investigator": offline_agents.run_investigator,
          "fixer_validator": offline_agents.run_fixer_validator}
FAKE_KEY = "FAKE-KEY-0000-NOT-A-REAL-SECRET"


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


class KillCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="saa-kill-")
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.count = 0
        _containment.drain_events()
        self.addCleanup(_containment.drain_events)

    def project(self, case="case_01_sqli_fstring"):
        self.count += 1
        dest = os.path.join(self.tmp, f"project{self.count}")
        shutil.copytree(os.path.join(ROOT, "golden", case), dest, ignore=shutil.ignore_patterns("expected.json"))
        return dest

    def start(self, project, agents=None, cls=Workflow):
        flow = cls(agents={**HONEST, **(agents or {})}, out_root=os.path.join(self.tmp, f"out{self.count}"))
        flow.start(project, RULES)
        return flow

    @staticmethod
    def approve(flow, decision="approved"):
        path = os.path.join(flow.run_dir, "review_queue.json")
        queue = json.loads(read_text(path))
        for proposal in queue["proposals"]:
            proposal.update(decision=decision, reviewer="test", reason="because")
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(queue, handle)

    def assert_killed(self, flow, criterion):
        """The run stopped, the alert was raised for exactly this criterion, and no report was written."""
        events = [e["event"] for e in flow.state["audit_log"]]
        self.assertEqual(flow.meta["phase"], "stopped", flow.meta.get("stop_reason"))
        self.assertEqual(flow.meta["alert"]["criterion"], criterion, flow.meta["alert"])
        self.assertIn(f"alert_kill_{criterion}", events)
        self.assertEqual(json.loads(read_text(os.path.join(flow.run_dir, "alert.json")))["criterion"], criterion)
        self.assertFalse(os.path.exists(os.path.join(flow.run_dir, "report.json")))
        self.assertFalse(os.path.exists(os.path.join(flow.run_dir, "fixes.patch")))


class TestKillChecks(KillCase):
    # 1 ------------------------------------------------------------------------------------------------
    def test_kill_original_modified(self):
        project = self.project()

        def careless(job):
            if job["job"] == "baseline_tests":
                with open(os.path.join(project, "src", "users.py"), "a", encoding="utf-8") as handle:
                    handle.write("\n# changed behind the orchestrator's back\n")
            return offline_agents.run_fixer_validator(job)
        flow = self.start(project, {"fixer_validator": careless})
        self.assert_killed(flow, "original_modified")
        self.assertEqual([h["agent"] for h in flow.state["handoff_log"]], ["auditor"])   # stopped at once, not at the end

    # 2 ------------------------------------------------------------------------------------------------
    def test_kill_write_outside_workspace(self):
        # (a) a tool call aimed at the original folder
        project = self.project()
        diff = "\n".join(["--- a/src/users.py", "+++ b/src/users.py", "@@ -1,1 +1,1 @@", "-x", "+y", ""])

        def aimed_at_original(job):
            client = McpClient("fixer-validator")
            try:
                client.call("apply_patch", {"workspace": project, "patch_diff": diff})
            finally:
                client.close()
            return offline_agents.run_fixer_validator(job)
        self.assert_killed(self.start(project, {"fixer_validator": aimed_at_original}), "write_outside_workspace")

        # (b) a file dropped beside the copy, with no tool involved
        project = self.project()

        def stray_file(job):
            with open(os.path.join(os.path.dirname(job["workspace"]), "leak.txt"), "w", encoding="utf-8") as handle:
                handle.write("x")
            return offline_agents.run_fixer_validator(job)
        self.assert_killed(self.start(project, {"fixer_validator": stray_file}), "write_outside_workspace")

    # 3 ------------------------------------------------------------------------------------------------
    def test_kill_network_not_approved(self):
        def phones_out(job):
            socket.create_connection(("example.test", 80), timeout=2)      # refused by the guard before any traffic
            return offline_agents.run_fixer_validator(job)
        self.assert_killed(self.start(self.project(), {"fixer_validator": phones_out}), "network_not_approved")

        def hides_it(job):
            try:
                socket.create_connection(("example.test", 80), timeout=2)
            except Exception:                                              # the agent swallows the refusal
                pass
            return offline_agents.run_fixer_validator(job)
        flow = self.start(self.project(), {"fixer_validator": hides_it})
        self.assert_killed(flow, "network_not_approved")                   # the guard remembered the attempt
        # the guard is off again once the run ends: nothing is left patched
        self.assertEqual(type(socket.socket.connect).__name__, "method_descriptor")

    # 4 ------------------------------------------------------------------------------------------------
    def test_kill_unmasked_secret(self):
        def leaky(job):
            out = offline_agents.run_auditor(job)
            if job["job"] == "audit":
                out["notes"] = [{"event": "agent_note", "detail": f'API_KEY = "{FAKE_KEY}"'}]
            return out
        flow = self.start(self.project(), {"auditor": leaky})
        self.assert_killed(flow, "unmasked_secret")
        everything = "".join(read_text(os.path.join(base, name)) for base, _d, files in os.walk(flow.run_dir) for name in files)
        self.assertNotIn(FAKE_KEY, everything)                             # the alert names the kind, never the value

    # 5 ------------------------------------------------------------------------------------------------
    def test_kill_fix_without_approval(self):
        # (a) a patch is prepared for a finding nobody approved
        class Eager(Workflow):
            def _apply_decisions(self, proposals):
                super()._apply_decisions(proposals)
                self.meta["approved_patches"].append(["F999", "--- a/x.py\n+++ b/x.py\n"])
        project = self.project()
        flow = self.start(project, cls=Eager)
        self.assertEqual(flow.meta["phase"], "waiting_for_review")
        self.approve(flow)
        flow.finish()
        self.assert_killed(flow, "fix_without_approval")

        # (b) fixes.patch appears although the person rejected every fix
        project = self.project()
        flow = self.start(project)
        self.approve(flow, "rejected")
        with open(os.path.join(flow.run_dir, "fixes.patch"), "w", encoding="utf-8") as handle:
            handle.write("--- a/src/users.py\n")
        flow.finish()
        self.assertEqual(flow.meta["phase"], "stopped")
        self.assertEqual(flow.meta["alert"]["criterion"], "fix_without_approval")
        self.assertFalse(os.path.exists(os.path.join(flow.run_dir, "report.json")))

    # 6 ------------------------------------------------------------------------------------------------
    def test_kill_audit_incomplete(self):
        # (a) a status is set but never logged
        class Forgetful(Workflow):
            def _status(self, finding_id, status, reason):
                rows = [r for r in self.state["finding_status"] if r["finding_id"] != finding_id]
                rows.append({"finding_id": finding_id, "status": status, "reason": reason})
                self.state["finding_status"] = sorted(rows, key=lambda r: r["finding_id"])
        flow = self.start(self.project("case_08_no_tests"), cls=Forgetful)
        self.assert_killed(flow, "audit_incomplete")

        # (b) the decision log cannot be written
        real = workflow_module._write_json

        def refuses_the_log(path, data):
            if os.path.basename(path) == "decision_log.json":
                raise OSError("disk full")
            return real(path, data)
        with mock.patch.object(workflow_module, "_write_json", refuses_the_log):
            flow = self.start(self.project("case_08_no_tests"))
        self.assert_killed(flow, "audit_incomplete")

    # 7 ------------------------------------------------------------------------------------------------
    def test_kill_package_changed(self):
        # (a) a package appears in the interpreter's environment during the run
        pkgs = os.path.join(self.tmp, "site")
        os.makedirs(os.path.join(pkgs, "fakepkg-1.0.dist-info"))
        with open(os.path.join(pkgs, "fakepkg-1.0.dist-info", "METADATA"), "w", encoding="utf-8") as handle:
            handle.write("Metadata-Version: 2.1\nName: fakepkg\nVersion: 1.0\n")
        self.addCleanup(lambda: sys.path.remove(pkgs) if pkgs in sys.path else None)

        def installs(job):
            sys.path.insert(0, pkgs)                                       # what an install would do to the environment
            return offline_agents.run_fixer_validator(job)
        flow = self.start(self.project(), {"fixer_validator": installs})
        self.assert_killed(flow, "package_changed")
        self.assertIn("fakepkg-1.0.dist-info", flow.meta["alert"]["detail"])
        sys.path.remove(pkgs)

        # (b) an install command is attempted through the test runner
        def pip_install(job):
            client = McpClient("fixer-validator")
            try:
                client.call("run_tests", {"workspace": job["workspace"], "test_command": "pip install requests", "timeout_seconds": 10})
            finally:
                client.close()
            return offline_agents.run_fixer_validator(job)
        self.assert_killed(self.start(self.project(), {"fixer_validator": pip_install}), "package_changed")

    # 8 ------------------------------------------------------------------------------------------------
    def test_kill_vcs_or_deploy(self):
        git = ["git", "-c", "user.name=test", "-c", "user.email=test@example.test"]
        # (a) a real commit lands in the repository that holds the original folder
        project = self.project()
        subprocess.run(["git", "init", "-q"], cwd=project, check=True)
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "initial"], cwd=project, check=True)

        def commits(job):
            subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "sneaky"], cwd=project, check=True)
            return offline_agents.run_fixer_validator(job)
        self.assert_killed(self.start(project, {"fixer_validator": commits}), "vcs_or_deploy")

        # (b) a push is attempted through the test runner
        def pushes(job):
            client = McpClient("fixer-validator")
            try:
                client.call("run_tests", {"workspace": job["workspace"], "test_command": "git push origin main", "timeout_seconds": 10})
            finally:
                client.close()
            return offline_agents.run_fixer_validator(job)
        self.assert_killed(self.start(self.project(), {"fixer_validator": pushes}), "vcs_or_deploy")


class TestKillChecksStayQuiet(KillCase):
    def test_an_honest_run_raises_no_alert(self):
        flow = self.start(self.project())
        self.assertEqual(flow.meta["phase"], "waiting_for_review")
        self.approve(flow)
        flow.finish()
        self.assertEqual(flow.meta["phase"], "done")
        self.assertNotIn("alert", flow.meta)
        self.assertFalse([e for e in flow.state["audit_log"] if e["event"].startswith("alert_")])

    def test_the_network_guard_is_removed_when_a_run_ends(self):
        before = socket.getaddrinfo
        self.start(self.project("case_04_safe_sql_lookalike"))
        self.assertIs(socket.getaddrinfo, before)

    def test_every_criterion_has_a_check_and_a_test(self):
        self.assertEqual([c for c, _ in kill_checks.CRITERIA], [c for c, _ in kill_checks.CHECKS])
        for criterion in (c for c, _ in kill_checks.CRITERIA):
            self.assertTrue(hasattr(TestKillChecks, f"test_kill_{criterion}"), criterion)


if __name__ == "__main__":
    unittest.main()
