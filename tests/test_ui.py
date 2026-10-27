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
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

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


class ConsoleStartupTest(unittest.TestCase):
    """A stale console must be obvious (a second console on the same port, running old code, kept answering)."""

    def serve(self):
        httpd = server.ConsoleServer(("127.0.0.1", 0), server.Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        self.addCleanup(httpd.server_close)
        self.addCleanup(httpd.shutdown)
        return httpd, httpd.server_address[1]

    def test_healthz_says_what_code_is_running(self):
        _httpd, port = self.serve()
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/healthz", timeout=5) as reply:
            body = reply.read().decode("utf-8")
            header = reply.headers["X-Console-Version"]
        lines = body.splitlines()
        self.assertEqual(lines[0], "ok")                                   # a health check or the launcher can still rely on line 1
        self.assertTrue(lines[1].startswith("version: "))
        self.assertIn(server.VERSION["code"], lines[1])
        self.assertRegex(server.VERSION["code"], r"^[0-9a-f]{10}$")
        self.assertIn(f"pid: {os.getpid()}", body)
        self.assertIn("folder: " + ROOT, body)
        self.assertEqual(header, f"{server.VERSION['commit']} {server.VERSION['code']}")

    def test_a_second_console_cannot_share_a_busy_port(self):
        _httpd, port = self.serve()
        with self.assertRaises(OSError):                                    # exclusive use on Windows, a normal bind failure elsewhere
            server.ConsoleServer(("127.0.0.1", port), server.Handler)
        described = server.whats_on_port("127.0.0.1", port)
        self.assertIn("a console:", described)
        self.assertIn(f"pid: {os.getpid()}", described)

    def test_main_refuses_to_start_on_a_busy_port_and_says_what_is_there(self):
        _httpd, port = self.serve()
        out = io.StringIO()
        old_argv, old_out = sys.argv, sys.stdout
        sys.argv, sys.stdout = ["server.py", "--port", str(port)], out
        try:
            code = server.main()
        finally:
            sys.argv, sys.stdout = old_argv, old_out
        self.assertEqual(code, 2)
        text = out.getvalue()
        self.assertIn(f"Port {port} is already in use", text)
        self.assertIn("a console:", text)
        self.assertIn(f"--port {port + 1}", text)

    def test_a_free_port_is_free_and_an_old_console_without_a_version_is_recognised(self):
        import socket
        probe = socket.socket()
        probe.bind(("127.0.0.1", 0))
        free = probe.getsockname()[1]
        probe.close()
        self.assertIsNone(server.whats_on_port("127.0.0.1", free))

        class OldConsole(BaseHTTPRequestHandler):                           # answers /healthz with just "ok", as before this change
            def do_GET(self):  # noqa: N802
                self.send_response(200)
                self.send_header("content-length", "2")
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *args):
                pass
        old = ThreadingHTTPServer(("127.0.0.1", 0), OldConsole)
        threading.Thread(target=old.serve_forever, daemon=True).start()
        self.addCleanup(old.server_close)
        self.addCleanup(old.shutdown)
        self.assertIn("older console that does not report its version", server.whats_on_port("127.0.0.1", old.server_address[1]))

    def test_the_launcher_only_opens_the_console_it_started(self):
        with open(os.path.join(ROOT, "launch.py"), encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("child.pid", text)                                    # compares the pid in /healthz with its own child
        self.assertIn("child.poll() is not None", text)                     # a refused start does not open another console's page


class ProviderTest(unittest.TestCase):
    """The console offers GPT, Claude and Gemini by name; the request format follows from the choice and is never asked for."""

    def tearDown(self):
        server.MODEL.update(cfg=None, source=None)

    def test_each_provider_sets_its_endpoint_and_format(self):
        for provider, style, host in (("openai", "openai", "api.openai.com"), ("anthropic", "anthropic", "api.anthropic.com"),
                                      ("google", "gemini", "generativelanguage.googleapis.com")):
            view = server.set_model({"provider": provider, "api_key": "k-not-real", "model": "any-model-name"})
            self.assertEqual(server.MODEL["cfg"].api_style, style)
            self.assertIn(host, view["endpoint"])
            self.assertEqual(view["provider"], provider)
            self.assertNotIn("k-not-real", json.dumps(view))                            # the key is never sent back
        self.assertNotIn("api_style", server.model_view())                              # no API-format field is exposed

    def test_the_provider_list_has_the_three_vendors_and_gateways(self):
        ids = [p["id"] for p in server.model_view()["providers"]]
        self.assertEqual(ids[:3], ["openai", "anthropic", "google"])
        self.assertIn("custom_openai", ids)

    def test_a_gateway_needs_its_endpoint_and_a_bad_model_name_is_refused(self):
        with self.assertRaises(ValueError):
            server.set_model({"provider": "custom_openai", "api_key": "k"})
        with self.assertRaises(ValueError):
            server.set_model({"provider": "openai", "api_key": "k", "model": "not a model; rm -rf"})
        view = server.set_model({"provider": "custom_openai", "api_key": "k", "endpoint": "https://gw.example.test/v1", "model": "m"})
        self.assertEqual(server.MODEL["cfg"].api_style, "openai")
        self.assertEqual(view["provider"], "custom_openai")

    def test_there_is_no_consent_checkbox_to_tick(self):
        server.set_model({"provider": "openai", "api_key": "k", "model": "gpt-5"})
        cfg, use = server.parse_use_model({"use_model": {"auditor": True}})            # no model_ack needed
        self.assertIsNotNone(cfg)
        self.assertTrue(use["auditor"])


class LiveStepsTest(unittest.TestCase):
    """The console shows what a scan is doing, step by step. The steps hold names and counts only, never code."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="saa-steps-test-")
        server.DATA = cls.tmp
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def get(self, path, data=None):
        req = urllib.request.Request(self.base + path, data=json.dumps(data).encode() if data is not None else None,
                                     headers={"Content-Type": "application/json"} if data is not None else {})
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    def test_steps_arrive_in_order_and_since_returns_only_the_new_ones(self):
        job = self.get("/api/jobs", {"case": "case_01_sqli_fstring"})["job_id"]
        for _ in range(300):
            v = self.get("/api/jobs/" + job)
            if v["phase"] in ("waiting_for_review", "done", "stopped", "error"):
                break
            time.sleep(0.2)
        steps = v["steps"]
        self.assertEqual(v["phase"], "waiting_for_review",
                         f"the run did not reach the review: error={v.get('error')!r}, stop_reason={(v.get('meta') or {}).get('stop_reason')!r}, "
                         f"last steps={[x['text'][:60] for x in steps[-3:]]}")
        self.assertEqual(v["steps_total"], len(steps))
        kinds = {s["kind"] for s in steps}
        self.assertTrue({"agent", "tool", "log"} <= kinds, kinds)
        texts = " | ".join(s["text"] for s in steps)
        self.assertIn("Running the security rules", texts)
        self.assertIn("Tests: pass", texts)
        self.assertIn("Re-check: clear", texts)
        self.assertEqual([s["t"] for s in steps], sorted(s["t"] for s in steps))        # in the order they happened
        cut = len(steps) - 3
        later = self.get(f"/api/jobs/{job}?since={cut}")
        self.assertEqual(later["steps"], steps[cut:])                                   # only what the page has not seen
        self.assertEqual(self.get(f"/api/jobs/{job}?since=999")["steps"], [])
        source = open(os.path.join(ROOT, "golden", "case_01_sqli_fstring", "src", "users.py"), encoding="utf-8").read()
        self.assertNotIn("SELECT id, name FROM users", json.dumps(steps))                # no code in the live view
        self.assertTrue(source)


if __name__ == "__main__":
    unittest.main()
