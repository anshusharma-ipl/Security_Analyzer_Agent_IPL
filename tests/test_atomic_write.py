"""The run files are written by write-then-replace. On Windows the replace can fail for a moment with "access denied" while the
console or a virus scanner has the file open; the write must retry instead of ending the run."""
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from orchestrator import workflow  # noqa: E402


class AtomicWriteTest(unittest.TestCase):
    def test_a_brief_access_denied_is_retried(self):
        real = os.replace
        calls = []

        def flaky(src, dst):
            calls.append(1)
            if len(calls) < 3:
                raise PermissionError(5, "Access is denied")
            return real(src, dst)

        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "state.json")
            with mock.patch.object(workflow.os, "replace", flaky):
                workflow._write_json(path, {"ok": True})
            self.assertEqual(json.load(open(path, encoding="utf-8")), {"ok": True})
        self.assertEqual(len(calls), 3)

    def test_a_lasting_failure_still_raises(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "state.json")
            with mock.patch.object(workflow.os, "replace", side_effect=PermissionError(5, "Access is denied")), \
                    mock.patch.object(workflow.time, "sleep"):
                with self.assertRaises(PermissionError):
                    workflow._write_json(path, {"ok": True})


if __name__ == "__main__":
    unittest.main()
