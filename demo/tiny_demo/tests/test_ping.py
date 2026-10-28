import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from ping import check_host


class Tests(unittest.TestCase):
    def test_reachable(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        with patch("ping.subprocess.run", return_value=mock_result):
            self.assertTrue(check_host("example.test"))

    def test_unreachable(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        with patch("ping.subprocess.run", return_value=mock_result):
            self.assertFalse(check_host("dead.host"))


if __name__ == "__main__":
    unittest.main()
