import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from greeting import greet


class Tests(unittest.TestCase):
    def test_greet(self):
        self.assertEqual(greet("Sam"), "Hello, Sam")

    def test_greet_other(self):
        self.assertEqual(greet("Ana"), "Hello, Ana")


if __name__ == "__main__":
    unittest.main()
