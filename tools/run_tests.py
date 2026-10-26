"""run_tests: run the project's own tests in the temporary copy (changes nothing).
Used by: Fixer & Validator.

  - the workspace must be a temporary copy registered by make_temp_copy; the original
    folder is refused, so tests never run (and never write bytecode, caches or files) there;
  - the command runs WITHOUT a shell (argv only), so ``;``, ``&&`` and ``|`` are plain text;
  - the environment is scrubbed: only PATH and the few variables Python needs are passed on,
    so no credentials or tokens from the caller's environment reach the tests;
  - a timeout kills the whole process tree;
  - exit 0 = pass, any other exit = fail; no tests = none (missing folder passed to ``-s``,
    "Ran 0 tests", or pytest exit 5). Output is tailed and secrets, emails and phones are hidden.
This does NOT block the network or the filesystem outside the copy. That is the container's
job at the pilot (AGENTS.md: isolation).
"""
from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import time

from . import _schema
from ._mask import Masker
from ._safety import SafetyError
from ._workspace import require_temp_copy

TOOL = "run_tests"
HANDLING = "not_verified_tell_person"
TAIL_CHARS = 2000
_KEEP = ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT", "TEMP", "TMP", "TMPDIR", "LANG", "LC_ALL")
_PYTHON = {"python", "python3", "py"}


def scrubbed_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k.upper() in _KEEP}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1", "CI": "1"})
    return env


def _kill_tree(proc: subprocess.Popen) -> None:
    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)], capture_output=True, timeout=10)
        else:
            import signal
            os.killpg(proc.pid, signal.SIGKILL)
    except (OSError, subprocess.SubprocessError):
        pass
    proc.kill()


def _missing_start_dir(argv: list[str], cwd: str) -> bool:
    """True when the command passes ``-s <folder>`` and that folder does not exist."""
    for flag, value in zip(argv, argv[1:]):
        if flag in ("-s", "--start-directory") and not os.path.isdir(os.path.join(cwd, value)):
            return True
    return False


def run_tests(workspace: str, test_command: str, timeout_seconds: int) -> dict:
    args = {"workspace": workspace, "test_command": test_command, "timeout_seconds": timeout_seconds}
    _schema.validate_args(TOOL, args)

    if not os.path.isdir(workspace):
        return _schema.fail(TOOL, args, "workspace_not_found", f"workspace {workspace!r} is not a folder", HANDLING)
    try:
        require_temp_copy(workspace)
    except SafetyError as exc:
        return _schema.fail(TOOL, args, "outside_workspace", str(exc), HANDLING)

    try:
        argv = shlex.split(test_command)
    except ValueError as exc:
        return _schema.fail(TOOL, args, "command_not_found", f"test_command cannot be read: {exc}", HANDLING)
    if not argv:
        return _schema.fail(TOOL, args, "command_not_found", "test_command is empty", HANDLING)

    cwd, env = os.path.realpath(workspace), scrubbed_env()
    if argv[0].lower().removesuffix(".exe") in _PYTHON:
        argv[0] = sys.executable                      # the interpreter running this tool
    else:
        found = shutil.which(argv[0], path=env.get("PATH"))
        if found is None:
            return _schema.fail(TOOL, args, "command_not_found", f"command {argv[0]!r} was not found", HANDLING)
        argv[0] = found

    if _missing_start_dir(argv, cwd):
        return _schema.ok(TOOL, args, {"outcome": "none", "exit_code": None, "duration_seconds": 0.0,
                                       "output_tail": "no tests: the test folder does not exist"})

    kwargs = ({"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True})
    started = time.monotonic()
    with tempfile.TemporaryFile() as sink:
        try:
            proc = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=sink,
                                    stderr=subprocess.STDOUT, **kwargs)
        except OSError as exc:
            return _schema.fail(TOOL, args, "command_not_found", f"cannot start {argv[0]!r}: {exc}", HANDLING)
        try:
            proc.wait(timeout=timeout_seconds)
        except subprocess.TimeoutExpired:
            _kill_tree(proc)
            proc.wait()
            return _schema.fail(TOOL, args, "timeout", f"tests did not finish within {timeout_seconds} seconds "
                                "and were stopped", HANDLING)
        sink.seek(0)
        output = sink.read().decode("utf-8", errors="replace")
    duration = round(time.monotonic() - started, 3)

    no_tests = "Ran 0 tests" in output or (proc.returncode == 5 and "pytest" in " ".join(argv).lower())
    outcome = "none" if no_tests else ("pass" if proc.returncode == 0 else "fail")
    tail = Masker().text(output)[-TAIL_CHARS:]
    return _schema.ok(TOOL, args, {"outcome": outcome, "exit_code": proc.returncode, "duration_seconds": duration,
                                   "output_tail": tail})
