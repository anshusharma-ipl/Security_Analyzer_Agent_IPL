import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from reports import greet


class Tests(unittest.TestCase):
    def test_greet(self):
        self.assertEqual(greet(), "ready")


if __name__ == "__main__":
    unittest.main()
