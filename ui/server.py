"""Web console for the Security Analyzer Agent. Python standard library plus jsonschema (AGENTS.md section 8).

    python ui/server.py            # then open http://127.0.0.1:8765

What it does: lets a person upload a Python project (a .zip, a picked folder, or one of the golden cases), runs the
REAL workflow orchestrator on it, shows every handoff live, lets the person approve / edit / reject each proposed
fix, and offers the report and fixes.patch for download.

What it does NOT do: it never changes the uploaded project and never applies a patch. By default the three agents are
the offline stand-ins in agents/offline_agents.py. In the Model panel (or with AI_MODEL_ENDPOINT / AI_MODEL_NAME /
ANTHROPIC_API_KEY in the environment or .env) a person can connect an Anthropic Messages-API endpoint and choose which
agents use it (agents/model_agents.py). The API key is held in memory only: never saved, never returned to the
page. The server listens on 127.0.0.1 only. NOTE: the project's own tests are executed on this computer (that is how a fix is verified),
so upload only code you trust. A container comes at the pilot (AGENTS.md section 8).
"""
from __future__ import annotations

import argparse
import base64
import hmac
import io
import json
import os
import re
import shutil
import sys
import threading
import time
import traceback
import uuid
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, unquote, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from orchestrator.workflow import DEFAULT_POLICY, RunStopped, StillWaiting, Workflow  # noqa: E402
from ui.report_html import render_report_html  # noqa: E402
from agents import model_agents  # noqa: E402

DATA = os.path.join(ROOT, "ui_data")                 # ignored by git; outside every uploaded project
GOLDEN = os.path.join(ROOT, "golden")
DEFAULT_RULES = os.path.join(GOLDEN, "rules.json")
MAX_ZIP_BYTES = 20 * 1024 * 1024
MAX_UNZIPPED_BYTES = 40 * 1024 * 1024
MAX_FILES = 2000
MAX_JSON_BYTES = 60 * 1024 * 1024
ID = re.compile(r"^[a-f0-9]{12}$")
DOWNLOADS = {"report.html": "text/html; charset=utf-8", "report.md": "text/markdown; charset=utf-8",
             "report.json": "application/json", "fixes.patch": "text/x-diff; charset=utf-8",
             "decision_log.json": "application/json", "state.json": "application/json"}

TOKEN = os.environ.get("CONSOLE_TOKEN", "")          # when set, every request needs it (see docs/DEPLOY.md)
ALLOWED_HOSTS = {"127.0.0.1", "localhost", "[::1]"} | {h.strip() for h in os.environ.get("CONSOLE_ALLOWED_HOSTS", "").split(",") if h.strip()}
MODEL: dict = {"cfg": None, "source": None}          # the connected model; the key lives only here, in memory
AGENT_KEYS = model_agents.AGENT_KEYS
JOBS: dict[str, dict] = {}
RUN_LOCK = threading.Lock()                          # one run at a time: tools keep a process-wide event list


# --------------------------------------------------------------------------- model connection
def model_view() -> dict:
    cfg = MODEL["cfg"]
    env = model_agents.ModelConfig.from_env()
    return {"configured": cfg is not None, "endpoint": cfg.endpoint if cfg else None, "model": cfg.model if cfg else None,
            "api_style": cfg.api_style if cfg else None, "source": MODEL["source"], "env_available": env is not None,
            "default_endpoint": model_agents.DEFAULT_ENDPOINT, "default_model": model_agents.DEFAULT_MODEL,
            "agents": list(AGENT_KEYS)}                      # never the key, not even part of it


def set_model(payload: dict) -> dict:
    if payload.get("from_env"):
        cfg, source = model_agents.ModelConfig.from_env(), "environment / .env"
        if cfg is None:
            raise ValueError("no ANTHROPIC_API_KEY, OPENAI_API_KEY or AI_API_KEY in the environment or .env")
    else:
        key = str(payload.get("api_key") or "").strip()
        if not key:
            raise ValueError("an API key is required")
        endpoint = str(payload.get("endpoint") or model_agents.DEFAULT_ENDPOINT).strip().rstrip("/")
        name = str(payload.get("model") or model_agents.DEFAULT_MODEL).strip()
        if not re.match(r"^https?://[^\s]+$", endpoint) or not re.match(r"^[A-Za-z0-9._:/-]{1,100}$", name):
            raise ValueError("endpoint must be an http(s) URL and the model name a plain identifier")
        cfg, source = model_agents.ModelConfig(endpoint, name, key, api_style=str(payload.get("api_style") or "auto")), "entered in the console"
    MODEL["cfg"], MODEL["source"] = cfg, source
    return model_view()


def parse_use_model(payload: dict) -> tuple:
    """(cfg or None, use dict). A model is used only if one is connected, an agent is ticked, and the person has
    acknowledged that masked code is sent to the endpoint."""
    wanted = {k: bool((payload.get("use_model") or {}).get(k)) for k in AGENT_KEYS}
    if not any(wanted.values()):
        return None, wanted
    cfg = MODEL["cfg"]
    if cfg is None:
        raise ValueError("connect a model first, or untick the agents that should use it")
    if payload.get("model_ack") is not True:
        raise ValueError("confirm that masked code is sent to the model endpoint (use fake data until compliance signs off)")
    return cfg, wanted


# --------------------------------------------------------------------------- helpers
def _json_read(path: str):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def _safe_rel(name: str) -> str | None:
    """A relative POSIX path that stays inside the project, or None."""
    name = name.replace("\\", "/").lstrip("/")
    parts = [p for p in name.split("/") if p not in ("", ".")]
    if not parts or any(p == ".." or ":" in p for p in parts):
        return None
    return "/".join(parts)


def _single_top_folder(folder: str) -> str:
    """Zips usually hold one top-level folder; scan inside it."""
    entries = [e for e in os.listdir(folder) if e not in ("__MACOSX",)]
    if len(entries) == 1 and os.path.isdir(os.path.join(folder, entries[0])):
        return os.path.join(folder, entries[0])
    return folder


def save_zip(data: bytes) -> str:
    if len(data) > MAX_ZIP_BYTES:
        raise ValueError(f"the zip is larger than {MAX_ZIP_BYTES // (1024 * 1024)} MB")
    try:
        archive = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ValueError("that is not a valid .zip file") from None
    infos = [i for i in archive.infolist() if not i.is_dir()]
    if len(infos) > MAX_FILES:
        raise ValueError(f"more than {MAX_FILES} files in the zip")
    if sum(i.file_size for i in infos) > MAX_UNZIPPED_BYTES:
        raise ValueError("the zip is too large when unpacked")
    upload_id = uuid.uuid4().hex[:12]
    dest = os.path.join(DATA, "uploads", upload_id)
    os.makedirs(dest)
    for info in infos:
        if (info.external_attr >> 16) & 0o170000 == 0o120000:
            continue                                  # a symlink inside the zip is never unpacked
        rel = _safe_rel(info.filename)
        if rel is None or rel.startswith("__MACOSX/"):
            continue
        target = os.path.join(dest, *rel.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with archive.open(info) as src, open(target, "wb") as out:
            out.write(src.read())
    if not any(files for _r, _d, files in os.walk(dest)):
        raise ValueError("the zip holds no files")
    return upload_id


def save_files(files: list) -> str:
    if not isinstance(files, list) or not files:
        raise ValueError("no files were sent")
    if len(files) > MAX_FILES:
        raise ValueError(f"more than {MAX_FILES} files")
    upload_id = uuid.uuid4().hex[:12]
    dest = os.path.join(DATA, "uploads", upload_id)
    os.makedirs(dest)
    for item in files:
        rel = _safe_rel(str(item.get("path", "")))
        if rel is None:
            continue
        target = os.path.join(dest, *rel.split("/"))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        with open(target, "wb") as out:
            out.write(base64.b64decode(item.get("b64", "")))
    if not any(files for _r, _d, files in os.walk(dest)):
        raise ValueError("no usable files were sent")
    return upload_id


def list_cases() -> list[dict]:
    cases = []
    for name in sorted(os.listdir(GOLDEN)):
        folder = os.path.join(GOLDEN, name)
        key = os.path.join(folder, "expected.json")
        if name.startswith("case_") and os.path.isfile(key):
            expected = _json_read(key)
            cases.append({"id": name, "category": expected.get("category", ""),
                          "expected_status": expected.get("expected_status", "")})
    return cases


def _phase(job: dict) -> str:
    if job.get("error"):
        return "error"
    run_dir = job.get("run_dir")
    if run_dir and os.path.isfile(os.path.join(run_dir, "run_meta.json")):
        try:
            meta = _json_read(os.path.join(run_dir, "run_meta.json"))
        except ValueError:
            return "running"
        if job.get("busy") and meta.get("phase") == "waiting_for_review":
            return "running"                          # the review was just submitted and is being finished
        return meta.get("phase", "running")
    return "running" if job.get("busy") else "queued"


# --------------------------------------------------------------------------- the run (background thread)
def _start_job(upload_dir: str, rules_path: str, policy: dict, label: str, cfg=None, use=None) -> str:
    job_id = uuid.uuid4().hex[:12]
    out_root = os.path.join(DATA, "out", job_id)
    job = {"id": job_id, "label": label, "model_used": [k for k, v in (use or {}).items() if v] if cfg else [], "source": upload_dir, "rules": rules_path, "out_root": out_root,
           "run_dir": None, "busy": True, "error": None, "review_error": None, "created": time.time()}
    JOBS[job_id] = job

    def work() -> None:
        with RUN_LOCK:
            try:
                flow = Workflow(agents=model_agents.make_agents(cfg, use) if cfg else None, out_root=out_root,
                                ai_model=cfg.record() if cfg else None)
                job["flow"] = flow
                try:
                    flow.start(upload_dir, rules_path, policy)
                finally:
                    job["run_dir"] = flow.run_dir or None
            except Exception as exc:  # noqa: BLE001 - the page must show the reason, not hang
                job["error"] = f"{type(exc).__name__}: {exc}"
                traceback.print_exc()
            finally:
                job["busy"] = False

    # run_dir is only known once Workflow.start() creates it, so wait for it from a helper that watches the folder
    def watch() -> None:
        for _ in range(600):
            if job["run_dir"] or not job["busy"]:
                return
            if os.path.isdir(out_root):
                made = [d for d in os.listdir(out_root) if d.startswith("run-")]
                if made:
                    job["run_dir"] = os.path.join(out_root, sorted(made)[-1])
                    return
            time.sleep(0.05)

    threading.Thread(target=work, daemon=True).start()
    threading.Thread(target=watch, daemon=True).start()
    return job_id


def _finish_job(job: dict) -> None:
    def work() -> None:
        with RUN_LOCK:
            try:
                flow = Workflow.load(job["run_dir"])
                flow.finish()
                job["review_error"] = None
            except StillWaiting as exc:
                job["review_error"] = str(exc)
            except RunStopped as exc:
                job["review_error"] = None
                job["error"] = None
                print("run stopped:", exc)
            except Exception as exc:  # noqa: BLE001
                job["error"] = f"{type(exc).__name__}: {exc}"
                traceback.print_exc()
            finally:
                job["busy"] = False

    job["busy"] = True
    threading.Thread(target=work, daemon=True).start()


def apply_review(job: dict, decisions: list) -> None:
    run_dir = job["run_dir"]
    path = os.path.join(run_dir, "review_queue.json")
    queue = _json_read(path)
    by_id = {d.get("finding_id"): d for d in decisions if isinstance(d, dict)}
    for proposal in queue["proposals"]:
        d = by_id.get(proposal["finding_id"])
        if not d or d.get("decision") not in ("approved", "edited", "rejected"):
            raise ValueError(f"choose approve, edit or reject for {proposal['finding_id']}")
        reviewer = str(d.get("reviewer") or "").strip()
        reason = str(d.get("reason") or "").strip()
        if not reviewer:
            raise ValueError("enter your name as the reviewer")
        if d["decision"] in ("edited", "rejected") and not reason:
            verb = "reject" if d["decision"] == "rejected" else "edit"
            raise ValueError(f"a reason is required to {verb} {proposal['finding_id']}")
        edited = None
        if d["decision"] == "edited":
            edited = str(d.get("edited_patch_diff") or "")
            if not edited.strip():
                raise ValueError(f"paste your edited diff for {proposal['finding_id']}")
            if not edited.endswith("\n"):
                edited += "\n"
        proposal.update(decision=d["decision"], reviewer=reviewer, reason=reason, edited_patch_diff=edited)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(queue, handle, indent=2)
    job["review_error"] = None
    _finish_job(job)


# --------------------------------------------------------------------------- views
def job_view(job: dict) -> dict:
    view = {"id": job["id"], "label": job["label"], "model_used": job.get("model_used", []), "phase": _phase(job), "error": job.get("error"),
            "review_error": job.get("review_error")}
    run_dir = job.get("run_dir")
    if not run_dir:
        return view
    for key, name in (("state", "state.json"), ("meta", "run_meta.json")):
        try:
            view[key] = _json_read(os.path.join(run_dir, name))
        except (OSError, ValueError):
            pass
    if "meta" in view:
        view["meta"].pop("originals_hash", None)      # large and not needed on the page
        view["meta"].pop("approved_patches", None)
    state = view.get("state")
    if state:
        for heavy in ("rules",):
            state.pop(heavy, None)
        state.pop("workspace", None)                  # a path inside this computer, not useful to show
    for key, name in (("review_queue", "review_queue.json"), ("report", "report.json")):
        try:
            view[key] = _json_read(os.path.join(run_dir, name))
        except (OSError, ValueError):
            pass
    view["downloads"] = [n for n in DOWNLOADS if n == "report.html" and "report" in view
                         or n != "report.html" and os.path.isfile(os.path.join(run_dir, n))]
    return view


def read_source_file(job: dict, rel: str) -> str:
    safe = _safe_rel(rel)
    if safe is None:
        raise ValueError("bad path")
    root = os.path.realpath(job["source"])
    path = os.path.realpath(os.path.join(root, *safe.split("/")))
    if os.path.commonpath([root, path]) != root or not os.path.isfile(path):
        raise FileNotFoundError(rel)
    with open(path, "rb") as handle:
        data = handle.read(400_000)
    return data.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- HTTP
class Handler(BaseHTTPRequestHandler):
    server_version = "SecurityAnalyzerConsole/1.0"

    def log_message(self, fmt, *args):  # quieter
        sys.stderr.write("[ui] " + fmt % args + "\n")

    # -- plumbing
    def _send(self, code: int, body: bytes, ctype: str, extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src https://fonts.gstatic.com; img-src 'self' data:")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, code: int, payload) -> None:
        self._send(code, json.dumps(payload).encode("utf-8"), "application/json")

    def _fail(self, code: int, message: str) -> None:
        self._json(code, {"error": message})

    def _body(self, limit: int) -> bytes:
        length = int(self.headers.get("Content-Length") or 0)
        if length > limit:
            raise ValueError("the upload is too large")
        return self.rfile.read(length)

    def _local_only(self) -> bool:
        """Host check (DNS-rebinding guard) and, when CONSOLE_TOKEN is set, the access token."""
        host = (self.headers.get("Host") or "").rsplit(":", 1)[0] if not (self.headers.get("Host") or "").startswith("[") else "[::1]"
        if host not in ALLOWED_HOSTS:
            self._fail(403, "this console does not answer on that host name")
            return False
        url = urlparse(self.path)
        if url.path == "/healthz":
            self._send(200, b"ok", "text/plain")
            return False
        if not TOKEN:
            return True
        supplied = parse_qs(url.query).get("token", [""])[0]
        if supplied and hmac.compare_digest(supplied, TOKEN):          # first visit: set a cookie, then drop the token from the URL
            self._send(302, b"", "text/plain", {"Location": url.path or "/",
                                                "Set-Cookie": f"saa_token={TOKEN}; HttpOnly; SameSite=Strict; Path=/"})
            return False
        cookie = {k.strip(): v for k, _, v in (c.partition("=") for c in (self.headers.get("Cookie") or "").split(";"))}
        if hmac.compare_digest(cookie.get("saa_token", ""), TOKEN):
            return True
        body = b"<!doctype html><meta charset=utf-8><title>Access token needed</title><p style='font:16px system-ui;max-width:40em;margin:3em auto'>This console needs an access token. Open it once with <code>/?token=YOUR_TOKEN</code>.</p>"
        self._send(401, body, "text/html; charset=utf-8")
        return False

    # -- routes
    def do_GET(self) -> None:  # noqa: N802
        if not self._local_only():
            return
        url = urlparse(self.path)
        path = url.path
        try:
            if path in ("/", "/index.html"):
                with open(os.path.join(HERE, "index.html"), "rb") as handle:
                    return self._send(200, handle.read(), "text/html; charset=utf-8")
            if path.startswith(("/static/", "/docs/")) or path == "/docs":
                return self._site(path)
            if path == "/api/model":
                return self._json(200, model_view())
            if path == "/api/info":
                return self._json(200, {"policy": DEFAULT_POLICY, "cases": list_cases(),
                                        "rules": _json_read(DEFAULT_RULES)["rules"],
                                        "busy": any(j.get("busy") for j in JOBS.values()), "model": model_view()})
            m = re.match(r"^/api/jobs/([a-f0-9]{12})(?:/(file|download/([a-z_.]+)))?$", path)
            if m and m.group(1) in JOBS:
                job = JOBS[m.group(1)]
                if m.group(2) is None:
                    return self._json(200, job_view(job))
                if m.group(2) == "file":
                    rel = parse_qs(url.query).get("path", [""])[0]
                    return self._json(200, {"path": rel, "text": read_source_file(job, unquote(rel))})
                return self._download(job, m.group(3))
            if path.startswith("/api/jobs/"):
                return self._fail(404, "unknown run")
            if path == "/api/rules":
                with open(DEFAULT_RULES, "rb") as handle:
                    return self._send(200, handle.read(), "application/json")
            self._fail(404, "not found")
        except FileNotFoundError:
            self._fail(404, "file not found")
        except ValueError as exc:
            self._fail(400, str(exc))

    def _site(self, path: str) -> None:
        """Static files: /static/* from ui/static, /docs/* from ui/site (the built guide). Nothing outside those folders."""
        base, rel = (os.path.join(HERE, "static"), path[len("/static/"):]) if path.startswith("/static/") \
            else (os.path.join(HERE, "site"), path[len("/docs/"):] if path != "/docs" else "guide.html")
        rel = unquote(rel) or "guide.html"
        target = os.path.realpath(os.path.join(base, rel))
        if not target.startswith(os.path.realpath(base) + os.sep) or not os.path.isfile(target):
            return self._fail(404, "not found")
        ctype = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".svg": "image/svg+xml", ".json": "application/json"}.get(os.path.splitext(target)[1], "application/octet-stream")
        with open(target, "rb") as handle:
            self._send(200, handle.read(), ctype)

    def _download(self, job: dict, name: str) -> None:
        run_dir = job.get("run_dir")
        if not run_dir:
            return self._fail(404, "nothing to download yet")
        if name == "bundle.zip":
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
                for fname in ("report.md", "report.json", "decision_log.json", "fixes.patch", "state.json"):
                    full = os.path.join(run_dir, fname)
                    if os.path.isfile(full):
                        archive.write(full, fname)
                if os.path.isfile(os.path.join(run_dir, "report.json")):
                    archive.writestr("report.html", self._report_html(run_dir))
            return self._send(200, buffer.getvalue(), "application/zip",
                              {"Content-Disposition": f'attachment; filename="security-analyzer-{job["id"]}.zip"'})
        inline = name == "report.view.html"
        if inline:
            name = "report.html"
        if name not in DOWNLOADS:
            return self._fail(404, "unknown file")
        if name == "report.html":
            if not os.path.isfile(os.path.join(run_dir, "report.json")):
                return self._fail(404, "the report is not written yet")
            body = self._report_html(run_dir).encode("utf-8")
        else:
            full = os.path.join(run_dir, name)
            if not os.path.isfile(full):
                return self._fail(404, f"{name} does not exist for this run")
            with open(full, "rb") as handle:
                body = handle.read()
        self._send(200, body, DOWNLOADS[name], {} if inline else {"Content-Disposition": f'attachment; filename="{name}"'})

    @staticmethod
    def _report_html(run_dir: str) -> str:
        report = _json_read(os.path.join(run_dir, "report.json"))
        try:
            state = _json_read(os.path.join(run_dir, "state.json"))
        except (OSError, ValueError):
            state = {}
        return render_report_html(report, state)

    def do_POST(self) -> None:  # noqa: N802
        if not self._local_only():
            return
        path = urlparse(self.path).path
        try:
            if path == "/api/upload/zip":
                return self._json(200, {"upload_id": save_zip(self._body(MAX_ZIP_BYTES))})
            if path == "/api/upload/files":
                payload = json.loads(self._body(MAX_JSON_BYTES) or b"{}")
                return self._json(200, {"upload_id": save_files(payload.get("files"))})
            if path == "/api/model":
                return self._json(200, set_model(json.loads(self._body(20_000) or b"{}")))
            if path == "/api/model/clear":
                MODEL["cfg"], MODEL["source"] = None, None
                return self._json(200, model_view())
            if path == "/api/model/test":
                if MODEL["cfg"] is None:
                    raise ValueError("connect a model first")
                return self._json(200, model_agents.test_connection(MODEL["cfg"]))
            if path == "/api/jobs":
                return self._create_job(json.loads(self._body(5_000_000) or b"{}"))
            m = re.match(r"^/api/jobs/([a-f0-9]{12})/review$", path)
            if m and m.group(1) in JOBS:
                job = JOBS[m.group(1)]
                if _phase(job) != "waiting_for_review":
                    return self._fail(409, "this run is not waiting for a review")
                payload = json.loads(self._body(5_000_000) or b"{}")
                apply_review(job, payload.get("decisions", []))
                return self._json(200, {"ok": True})
            self._fail(404, "not found")
        except (ValueError, KeyError) as exc:
            self._fail(400, str(exc))
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            self._fail(500, f"{type(exc).__name__}: {exc}")

    def _create_job(self, payload: dict) -> None:
        if any(j.get("busy") for j in JOBS.values()):
            return self._fail(409, "another run is in progress; wait for it to finish")
        # the project: a golden case or an upload
        if payload.get("case"):
            name = str(payload["case"])
            if not re.match(r"^case_[a-z0-9_]+$", name) or not os.path.isdir(os.path.join(GOLDEN, name)):
                raise ValueError("unknown golden case")
            # run on a COPY so even a bug could never touch golden/
            upload_id = uuid.uuid4().hex[:12]
            dest = os.path.join(DATA, "uploads", upload_id)
            shutil.copytree(os.path.join(GOLDEN, name), dest, ignore=shutil.ignore_patterns("expected.json", "__pycache__"))
            source, label = dest, name
        else:
            upload_id = str(payload.get("upload_id") or "")
            if not ID.match(upload_id) or not os.path.isdir(os.path.join(DATA, "uploads", upload_id)):
                raise ValueError("upload a project first")
            source = _single_top_folder(os.path.join(DATA, "uploads", upload_id))
            label = str(payload.get("label") or "uploaded project")[:80]
        # the rules file
        rules_text = payload.get("rules_text")
        rules_path = DEFAULT_RULES
        if rules_text:
            rules_path = os.path.join(DATA, "rules", f"{uuid.uuid4().hex[:12]}.json")
            os.makedirs(os.path.dirname(rules_path), exist_ok=True)
            with open(rules_path, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(str(rules_text))
        # only these two policy values may be changed from the page
        policy = {}
        for key, low, high in (("file_cap", 1, 1000), ("max_retries", 0, 3)):
            if payload.get("policy", {}).get(key) is not None:
                value = int(payload["policy"][key])
                if not low <= value <= high:
                    raise ValueError(f"{key} must be between {low} and {high}")
                policy[key] = value
        cfg, use = parse_use_model(payload)
        job_id = _start_job(source, rules_path, policy, label, cfg, use)
        self._json(200, {"job_id": job_id})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8765")))
    parser.add_argument("--host", default="127.0.0.1", help="use 0.0.0.0 only inside a container, with CONSOLE_TOKEN set")
    args = parser.parse_args()
    os.makedirs(DATA, exist_ok=True)
    if args.host not in ("127.0.0.1", "localhost", "::1") and not TOKEN:
        print("Refusing to listen on a network address without CONSOLE_TOKEN: this console runs the tests of uploaded code.")
        return 2
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Security Analyzer console on http://{args.host}:{args.port}  (Ctrl+C to stop)")
    print("Agents are offline stand-ins unless you connect a model in the Model panel. The project's tests run on this computer.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
