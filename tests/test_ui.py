"""Tests for the web console (ui/server.py): a full run over HTTP, the safety refusals, and that nothing original changes."""
import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
import zipfile
from http.server import ThreadingHTTPServer

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from ui import server  # noqa: E402
from tools.orchestrator_helpers import hash_originals  # noqa: E402


class ConsoleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="saa-ui-test-")
        server.DATA = cls.tmp
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.golden_hash = hash_originals(os.path.join(ROOT, "golden"))

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def call(self, path, data=None, raw=None):
        body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
        req = urllib.request.Request(self.base + path, data=body, headers={"Content-Type": "application/json"} if data is not None else {})
        try:
            with urllib.request.urlopen(req) as r:
                payload = r.read()
                return r.status, (json.loads(payload) if r.headers.get("Content-Type", "").startswith("application/json") else payload)
        except urllib.error.HTTPError as exc:
            return exc.code, json.loads(exc.read())

    def wait(self, job, phases):
        for _ in range(300):
            _s, v = self.call("/api/jobs/" + job)
            if v["phase"] in phases:
                return v
            time.sleep(0.2)
        self.fail("timeout waiting for " + str(phases))

    def test_guide_pages_are_served_and_nothing_outside_the_site_folders(self):
        s, body = self.call("/docs/guide.html")
        self.assertEqual(s, 200)
        self.assertIn(b"How the Security Analyzer works", body)
        self.assertEqual(self.call("/static/app.css")[0], 200)
        self.assertEqual(self.call("/docs/md/PRD.html")[0], 200)
        for bad in ("/docs/../server.py", "/static/../server.py", "/docs/%2e%2e/server.py", "/docs/nothing.html"):
            self.assertEqual(self.call(bad)[0], 404, bad)

    def test_access_token_when_one_is_set(self):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a, **k):
                return None
        opener = urllib.request.build_opener(NoRedirect)
        def get(path, cookie=None):
            req = urllib.request.Request(self.base + path, headers={"Cookie": cookie} if cookie else {})
            try:
                with opener.open(req) as r:
                    return r.status, r.headers
            except urllib.error.HTTPError as exc:
                return exc.code, exc.headers
        server.TOKEN = "t0k3n-for-tests"
        try:
            self.assertEqual(get("/api/info")[0], 401)
            self.assertEqual(get("/healthz")[0], 200)                       # health check needs no token
            code, headers = get("/?token=wrong")
            self.assertEqual(code, 401)
            code, headers = get("/?token=t0k3n-for-tests")
            self.assertEqual(code, 302)
            self.assertIn("saa_token=t0k3n-for-tests", headers["Set-Cookie"])
            self.assertEqual(get("/api/info", "saa_token=t0k3n-for-tests")[0], 200)
            self.assertEqual(get("/api/info", "saa_token=nope")[0], 401)
        finally:
            server.TOKEN = ""

    def test_full_run_approve_and_download(self):
        _s, r = self.call("/api/jobs", {"case": "case_01_sqli_fstring"})
        v = self.wait(r["job_id"], {"waiting_for_review", "done", "stopped", "error"})
        self.assertEqual(v["phase"], "waiting_for_review")
        proposal = v["review_queue"]["proposals"][0]
        self.assertIn("?", proposal["patch_diff"])
        s, _ = self.call(f"/api/jobs/{r['job_id']}/review", {"decisions": [{"finding_id": "F001", "decision": "approved", "reviewer": "Test"}]})
        self.assertEqual(s, 200)
        v = self.wait(r["job_id"], {"done", "stopped", "error"})
        self.assertEqual(v["phase"], "done")
        self.assertEqual(v["report"]["totals"]["fixed_and_verified"], 1)
        self.assertTrue(v["state"]["originals_unchanged"])
        s, body = self.call(f"/api/jobs/{r['job_id']}/download/fixes.patch")
        self.assertEqual(s, 200)
        self.assertIn(b"+++ b/src/users.py", body)
        s, body = self.call(f"/api/jobs/{r['job_id']}/download/report.html")
        self.assertEqual(s, 200)
        self.assertIn(b"Security Analyzer report", body)

    def test_reject_needs_a_reason_and_edit_must_verify(self):
        _s, r = self.call("/api/jobs", {"case": "case_01_sqli_fstring"})
        self.wait(r["job_id"], {"waiting_for_review"})
        s, err = self.call(f"/api/jobs/{r['job_id']}/review", {"decisions": [{"finding_id": "F001", "decision": "rejected", "reviewer": "T"}]})
        self.assertEqual(s, 400)
        self.assertIn("reason", err["error"])
        self.call(f"/api/jobs/{r['job_id']}/review", {"decisions": [{"finding_id": "F001", "decision": "edited", "reviewer": "T", "reason": "r", "edited_patch_diff": "not a diff"}]})
        time.sleep(1.5)
        _s, v = self.call("/api/jobs/" + r["job_id"])
        self.assertEqual(v["phase"], "waiting_for_review")
        self.assertIn("does not apply", v["review_error"])

    def test_no_tests_case_goes_to_a_person_without_waiting(self):
        _s, r = self.call("/api/jobs", {"case": "case_08_no_tests"})
        v = self.wait(r["job_id"], {"done", "waiting_for_review", "stopped", "error"})
        self.assertEqual(v["phase"], "done")
        self.assertEqual(v["report"]["totals"]["needs_a_person"], 1)

    def test_zip_slip_and_bad_input_are_refused(self):
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("../../escape.txt", "x")
            z.writestr("p/src/a.py", "x = 1\n")
        s, r = self.call("/api/upload/zip", raw=buf.getvalue())
        self.assertEqual(s, 200)
        self.assertFalse(os.path.exists(os.path.join(self.tmp, "escape.txt")))
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(self.tmp), "escape.txt")))
        s, _ = self.call("/api/upload/zip", raw=b"not a zip")
        self.assertEqual(s, 400)
        s, _ = self.call("/api/jobs", {"case": "../etc"})
        self.assertEqual(s, 400)

    def test_bad_rules_file_stops_at_step_1(self):
        _s, r = self.call("/api/jobs", {"case": "case_01_sqli_fstring", "rules_text": "{nope"})
        v = self.wait(r["job_id"], {"stopped", "error", "done", "waiting_for_review"})
        self.assertEqual(v["phase"], "stopped")
        self.assertIn("step 1", v["meta"]["stop_reason"])

    def test_golden_is_never_changed(self):
        self.assertEqual(hash_originals(os.path.join(ROOT, "golden")), self.golden_hash)


if __name__ == "__main__":
    unittest.main()
