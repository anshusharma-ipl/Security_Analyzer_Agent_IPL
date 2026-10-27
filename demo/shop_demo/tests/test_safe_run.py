import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from safe_run import run_python


class Tests(unittest.TestCase):
    def test_runs(self):
        self.assertEqual(run_python("x; echo not-a-shell"), 0)


if __name__ == "__main__":
    unittest.main()
