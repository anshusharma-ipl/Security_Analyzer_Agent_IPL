"""Immediate kill criteria (canvas section 16): one automatic check each. A check that fires stops the run and raises an alert.

    python kill_checks.py            # the table: criterion | check | test
    python kill_checks.py --run      # the same table with each test run, and its result

The orchestrator (orchestrator/workflow.py) calls check() after every agent handoff and once more before the report is
written. These checks are deliberately independent of the guards inside the tools: a tool refusing a bad request is the
first wall, and this module is the alarm that notices if anything got through, or was done without using a tool.

    original_modified        every original file is hashed again and compared with the hashes taken before the run
    write_outside_workspace  the temporary run folder holds only the copy and its marker; no write was aimed outside the copy
    network_not_approved     a guard on socket connects and DNS lookups refuses any host but the approved model endpoint
    unmasked_secret          nothing an agent hands over, and no log line, holds a secret, email or phone number
    fix_without_approval     every patch written for a person traces to an approved or edited decision with a reviewer
    audit_incomplete         the decision log has no gap: sequence, every handoff, every status, every approval
    package_changed          the installed package set is the same as before the run
    vcs_or_deploy            the git refs (HEAD, branches, remotes, packed refs, merge state) are unchanged, and no
                             commit, push, merge or deploy command was attempted

Limits, stated plainly: the network guard covers this Python process (the orchestrator and the stand-in agents), not the
child process that runs the project's tests; the package check sees the interpreter's installed distributions;
the container at the pilot (AGENTS.md section 8) is the hard wall for everything a child process can do.
"""
from __future__ import annotations

import hashlib
import os
import socket
import sys
from urllib.parse import urlsplit

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from tools import _containment  # noqa: E402
from tools.orchestrator_helpers import verify_originals  # noqa: E402

CRITERIA = [
    ("original_modified", "modifies an original file"),
    ("write_outside_workspace", "writes outside the temporary workspace"),
    ("network_not_approved", "contacts an unauthorized network endpoint"),
    ("unmasked_secret", "exposes an unmasked secret"),
    ("fix_without_approval", "applies a fix without approval"),
    ("audit_incomplete", "fails to create a complete audit log"),
    ("package_changed", "installs or removes a package"),
    ("vcs_or_deploy", "performs a commit, push, merge, or deployment"),
]
TESTS = {c: f"tests.test_kill_checks.TestKillChecks.test_kill_{c}" for c, _ in CRITERIA}


class KillSwitch(Exception):
    """A kill criterion fired. ``criterion`` is one of CRITERIA; ``detail`` never contains a secret."""

    def __init__(self, criterion: str, detail: str) -> None:
        super().__init__(f"{criterion}: {detail}")
        self.criterion, self.detail = criterion, detail


# ------------------------------------------------------------------ fingerprints
def find_git_dir(folder: str) -> str | None:
    """The .git folder of the repository that holds ``folder`` (walking up), or None."""
    current = os.path.realpath(folder)
    while True:
        dot = os.path.join(current, ".git")
        if os.path.isdir(dot):
            return dot
        if os.path.isfile(dot):                                   # a worktree: the file points at the real git dir
            with open(dot, encoding="utf-8", errors="replace") as handle:
                text = handle.read().strip()
            if text.startswith("gitdir:"):
                return os.path.realpath(os.path.join(current, text[7:].strip()))
        parent = os.path.dirname(current)
        if parent == current:
            return None
        current = parent


def git_fingerprint(folder: str) -> str:
    """One hash of everything a commit, push, merge, rebase or cherry-pick changes: HEAD, every ref, packed refs and
    the in-progress markers. 'no-git' when the folder is in no repository (a repository appearing later also differs)."""
    git = find_git_dir(folder)
    if git is None:
        return "no-git"
    digest = hashlib.sha256()

    def feed(label: str, path: str) -> None:
        try:
            with open(path, "rb") as handle:
                digest.update(label.encode() + b"=" + handle.read() + b"\n")
        except OSError:
            digest.update(label.encode() + b"=absent\n")

    for name in ("HEAD", "packed-refs", "MERGE_HEAD", "CHERRY_PICK_HEAD", "REVERT_HEAD", "REBASE_HEAD"):
        feed(name, os.path.join(git, name))
    for name in ("rebase-merge", "rebase-apply"):
        digest.update(f"{name}={os.path.isdir(os.path.join(git, name))}\n".encode())
    for base, dirs, files in os.walk(os.path.join(git, "refs")):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(base, name)
            feed("refs/" + os.path.relpath(full, os.path.join(git, "refs")).replace(os.sep, "/"), full)
    return digest.hexdigest()


def package_set() -> list[str]:
    """The installed distributions visible to this interpreter, as the .dist-info / .egg-info folder names on sys.path
    (they carry name and version, e.g. requests-2.31.0.dist-info). A listing, not a metadata read: it takes
    milliseconds, where importlib.metadata took about 1.7 seconds here and runs at every handoff."""
    found = set()
    for entry in sys.path:
        try:
            if os.path.isdir(entry):
                found.update(name for name in os.listdir(entry) if name.endswith((".dist-info", ".egg-info")))
        except OSError:
            continue
    return sorted(found)


def take_baseline(source_folder: str, temp_run_dir: str) -> dict:
    """What 'unchanged' means for this run. JSON-safe: it is saved in run_meta.json so a later process can compare."""
    return {"git": git_fingerprint(source_folder), "packages": package_set(), "run_dir": temp_run_dir,
            "run_dir_entries": sorted(os.listdir(temp_run_dir))}


# ------------------------------------------------------------------ the network guard
def approved_host(env_path: str | None = None) -> str | None:
    """The hostname of AI_MODEL_ENDPOINT in .env, or None when it is 'none' or unset."""
    path = env_path or os.path.join(ROOT, ".env")
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                key, sep, value = line.strip().partition("=")
                if sep and key.strip() == "AI_MODEL_ENDPOINT" and value.strip().lower() not in ("", "none"):
                    return urlsplit(value.strip()).hostname
    return None


class NetworkGuard:
    """While installed, a socket connect or DNS lookup to any host other than loopback and the approved model endpoint
    raises NetworkViolation, and the attempt is remembered in ``events`` even if the caller swallows the exception."""

    LOOPBACK = {"localhost", "127.0.0.1", "::1"}

    def __init__(self, approved: str | None = None) -> None:
        self.approved = approved if approved is not None else approved_host()
        self.events: list[str] = []
        self._saved: dict | None = None

    def allowed(self, host) -> bool:
        if not isinstance(host, str):
            return True                                           # a Unix-domain path or a raw number: no network host
        return host.lower() in self.LOOPBACK or host.startswith("127.") or (self.approved is not None and host.lower() == self.approved.lower())

    def _refuse(self, host) -> None:
        detail = f"a connection or lookup for {host!r} was attempted; only the approved model endpoint may be contacted"
        self.events.append(detail)
        _containment.record("alert_network_not_approved", detail)
        raise _containment.NetworkViolation(detail)

    def install(self) -> None:
        if self._saved is not None:
            return
        guard, real = self, {"connect": socket.socket.connect, "connect_ex": socket.socket.connect_ex,
                             "getaddrinfo": socket.getaddrinfo}
        self._saved = real

        def connect(sock, address):
            host = address[0] if isinstance(address, tuple) and address else None
            if not guard.allowed(host):
                guard._refuse(host)
            return real["connect"](sock, address)

        def connect_ex(sock, address):
            host = address[0] if isinstance(address, tuple) and address else None
            if not guard.allowed(host):
                guard._refuse(host)
            return real["connect_ex"](sock, address)

        def getaddrinfo(host, *args, **kwargs):
            if isinstance(host, (str, bytes)) and not guard.allowed(host.decode() if isinstance(host, bytes) else host):
                guard._refuse(host)
            return real["getaddrinfo"](host, *args, **kwargs)

        socket.socket.connect, socket.socket.connect_ex, socket.getaddrinfo = connect, connect_ex, getaddrinfo

    def uninstall(self) -> None:
        if self._saved is None:
            return
        socket.socket.connect, socket.socket.connect_ex = self._saved["connect"], self._saved["connect_ex"]
        socket.getaddrinfo = self._saved["getaddrinfo"]
        self._saved = None

    def __enter__(self):
        self.install()
        return self

    def __exit__(self, *exc):
        self.uninstall()


# ------------------------------------------------------------------ the eight checks
# Each takes ctx (point, base, state, meta, run_dir, output, guard) and returns a detail string when it fires.
def _events(*names: str) -> list[tuple[str, str]]:
    return [e for e in _containment.peek_events() if e[0] in names]


def check_original_modified(ctx):
    baseline = ctx["meta"].get("originals_hash")
    if not baseline:
        return None
    found = verify_originals(ctx["state"]["input"]["source_folder"], baseline)
    if found["unchanged"]:
        return None
    return f"changed {found['changed'][:3]}, added {found['added'][:3]}, removed {found['removed'][:3]}"


def check_write_outside_workspace(ctx):
    hits = _events("alert_write_outside_copy")
    if hits:
        return hits[0][1]
    run_dir = ctx["base"]["run_dir"]
    if os.path.isdir(run_dir) and sorted(os.listdir(run_dir)) != ctx["base"]["run_dir_entries"]:
        extra = sorted(set(os.listdir(run_dir)) ^ set(ctx["base"]["run_dir_entries"]))
        return f"the temporary run folder changed outside the copy: {extra[:3]}"
    return None


def check_network_not_approved(ctx):
    if ctx["guard"] is not None and ctx["guard"].events:
        return ctx["guard"].events[0]
    hits = _events("alert_network_not_approved")
    if hits:
        return hits[0][1]
    for _event, detail in _events("alert_forbidden_command"):
        if "network" in detail:
            return detail
    return None


def check_unmasked_secret(ctx):
    kinds = _containment.find_leaks(ctx["output"]) if ctx["output"] is not None else []
    kinds += _containment.find_leaks(ctx["state"]["audit_log"])
    kinds = sorted(set(kinds))
    return f"an unmasked {', '.join(kinds)} value was found in an agent output or the decision log" if kinds else None


def check_fix_without_approval(ctx):
    if ctx["point"] != "end":
        return None
    approved = {a["finding_id"] for a in ctx["state"]["approvals"]
                if a["decision"] in ("approved", "edited") and a.get("reviewer")}
    patches = [row[0] for row in ctx["meta"].get("approved_patches", [])]
    loose = sorted(set(patches) - approved)
    if loose:
        return f"a patch was prepared for {loose} without an approving decision and a named reviewer"
    if not patches and os.path.exists(os.path.join(ctx["run_dir"], "fixes.patch")):
        return "fixes.patch exists but no fix was approved"
    return None


def audit_gaps(state: dict, final: bool) -> list[str]:
    """What the decision log is missing. Empty when it is complete for this point of the run."""
    log = state["audit_log"]
    events = [e["event"] for e in log]
    gaps = []
    if [e["seq"] for e in log] != list(range(1, len(log) + 1)):
        gaps.append("the log sequence has a gap")
    for needed in ("run_started", "rules_validated", "temporary_copy_made") + (("originals_verified",) if final else ()):
        if needed not in events:
            gaps.append(f"no {needed} entry")
    closed = sum(1 for e in events if e.endswith("_done") or e in ("agent_failed", "invalid_output"))
    if closed < len(state["handoff_log"]):
        gaps.append(f"{len(state['handoff_log']) - closed} handoff(s) have no log entry")
    if final:
        for row in state["finding_status"]:
            if not any(e["event"] == "status_set" and e.get("finding_id") == row["finding_id"] for e in log):
                gaps.append(f"no status_set entry for {row['finding_id']}")
        for approval in state["approvals"]:
            if not any(e["actor"] == "person" and e.get("finding_id") == approval["finding_id"] for e in log):
                gaps.append(f"no log entry for the decision on {approval['finding_id']}")
        if state.get("candidate_findings") and "review_queue_written" not in events:
            gaps.append("no review_queue_written entry")
    return gaps


def check_audit_incomplete(ctx):
    gaps = audit_gaps(ctx["state"], ctx["point"] == "end")
    return "; ".join(gaps[:3]) if gaps else None


def check_package_changed(ctx):
    now, before = set(package_set()), set(ctx["base"]["packages"])
    if now != before:
        return f"installed packages changed: added {sorted(now - before)[:3]}, removed {sorted(before - now)[:3]}"
    for _event, detail in _events("alert_forbidden_command"):
        if "package" in detail:
            return detail
    return None


def check_vcs_or_deploy(ctx):
    if git_fingerprint(ctx["state"]["input"]["source_folder"]) != ctx["base"]["git"]:
        return "the git refs of the repository holding the original folder changed (a commit, push, merge or similar)"
    for _event, detail in _events("alert_forbidden_command"):
        if "git" in detail or "deploy" in detail:
            return detail
    return None


CHECKS = [
    ("original_modified", check_original_modified),
    ("write_outside_workspace", check_write_outside_workspace),
    ("network_not_approved", check_network_not_approved),
    ("unmasked_secret", check_unmasked_secret),
    ("fix_without_approval", check_fix_without_approval),
    ("audit_incomplete", check_audit_incomplete),
    ("package_changed", check_package_changed),
    ("vcs_or_deploy", check_vcs_or_deploy),
]


def check(point: str, base: dict, state: dict, meta: dict, run_dir: str, output=None, guard=None) -> None:
    """Run all eight checks. ``point`` is 'handoff' (after an agent returned, before its output is merged) or 'end'
    (before the report is written). Raises KillSwitch for the first criterion that fires."""
    ctx = {"point": point, "base": base, "state": state, "meta": meta, "run_dir": run_dir, "output": output, "guard": guard}
    for criterion, fn in CHECKS:
        detail = fn(ctx)
        if detail:
            raise KillSwitch(criterion, detail)


# ------------------------------------------------------------------ the table
def table(run: bool) -> int:
    import io
    import unittest

    sys.stdout.reconfigure(encoding="utf-8")
    fns = dict(CHECKS)
    rows, failed = [], 0
    for criterion, text in CRITERIA:
        result = "(not run; use --run)"
        if run:
            suite = unittest.defaultTestLoader.loadTestsFromName(TESTS[criterion])
            outcome = unittest.TextTestRunner(stream=io.StringIO(), verbosity=0).run(suite)
            result = "PASS (the run stopped)" if outcome.wasSuccessful() else "FAIL"
            failed += not outcome.wasSuccessful()
        rows.append((text, f"kill_checks.{fns[criterion].__name__}", TESTS[criterion].split(".")[-1], result))
    widths = [max(len(r[i]) for r in rows + [("kill criterion", "check", "test", "result")]) for i in range(4)]
    for r in [("kill criterion", "check", "test", "result")] + rows:
        print(" | ".join(cell.ljust(widths[i]) for i, cell in enumerate(r)))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(table("--run" in sys.argv[1:]))
