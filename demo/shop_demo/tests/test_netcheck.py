import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from netcheck import check_host


class Tests(unittest.TestCase):
    def test_one(self):
        self.assertEqual(check_host("example.test"), "checking example.test")

    def test_two(self):
        self.assertEqual(check_host("10.0.0.1"), "checking 10.0.0.1")


if __name__ == "__main__":
    unittest.main()
