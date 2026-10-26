"""Records real console runs from a running console (python ui/server.py) into ui/replay/recorded.json.

    python ui/replay/record.py [http://127.0.0.1:8765]

The replay page (build.py) plays these back with no server, so a static host can show the real console UI.
Nothing is made up: every view is what the server returned for a real run with the offline stand-in agents.
"""
import json
import os
import re
import sys
import time
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
CASES = ["case_01_sqli_fstring", "case_09_injection_comment_sqli", "case_08_no_tests"]
HERE = os.path.dirname(os.path.abspath(__file__))


def call(path, data=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(data).encode() if data is not None else None,
                                 headers={"Content-Type": "application/json"} if data is not None else {})
    with urllib.request.urlopen(req) as r:
        return json.loads(r.read())


def wait(job, phases):
    for _ in range(300):
        v = call("/api/jobs/" + job)
        if v["phase"] in phases:
            return v
        time.sleep(0.2)
    raise SystemExit("timeout")


def clean(obj):
    """Drop anything that names this computer."""
    obj = dict(obj)
    if "meta" in obj:                                   # run bookkeeping that names this computer's folders
        obj["meta"] = {k: v for k, v in obj["meta"].items() if k in ("phase", "stop_reason")}
    text = json.dumps(obj)
    text = re.sub(r"/(tmp|home|root|usr|var|mnt)/[^\"\\ ]*", "<path>", text)
    return json.loads(text)


info = call("/api/info")
rec = {"info": {"policy": info["policy"], "rules": info["rules"], "cases": [c for c in info["cases"] if c["id"] in CASES], "busy": False,
                "model": {"configured": False, "endpoint": None, "model": None, "source": None, "env_available": False,
                          "default_endpoint": "https://api.anthropic.com", "default_model": "claude-sonnet-5-5", "agents": ["auditor", "investigator", "fixer_validator"]}},
       "cases": {}, "recorded_on": time.strftime("%Y-%m-%d")}
for case in CASES:
    job = call("/api/jobs", {"case": case})["job_id"]
    views = [wait(job, {"waiting_for_review", "done", "stopped", "error"})]
    files = {}
    if views[0]["phase"] == "waiting_for_review":
        decisions = [{"finding_id": p["finding_id"], "decision": "approved", "reviewer": "Demo reviewer", "reason": ""} for p in views[0]["review_queue"]["proposals"]]
        call(f"/api/jobs/{job}/review", {"decisions": decisions})
        views.append(wait(job, {"done", "stopped", "error"}))
    rows = []
    for v in views:
        for f in (v.get("report") or {}).get("findings", []) + [p for p in (v.get("review_queue") or {}).get("proposals", [])]:
            rows.append(f["file"])
        for c in (v.get("state") or {}).get("candidate_findings", []):
            rows.append(c["file"])
    for path in sorted(set(rows)):
        files[path] = call(f"/api/jobs/{job}/file?path={path}")["text"]
    label = next(c["category"] for c in info["cases"] if c["id"] == case)
    rec["cases"][case] = {"label": label, "views": [clean(v) for v in views], "files": files}
    print(case, [v["phase"] for v in views], list(files))
with open(os.path.join(HERE, "recorded.json"), "w", encoding="utf-8") as handle:
    json.dump(rec, handle, ensure_ascii=False)
