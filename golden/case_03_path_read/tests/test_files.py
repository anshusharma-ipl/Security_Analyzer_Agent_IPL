import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import tempfile

from files import read_file


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        with open(os.path.join(self.tmp.name, "a.txt"), "w") as f:
            f.write("hello")

    def test_reads_file(self):
        self.assertEqual(read_file(self.tmp.name, "a.txt"), "hello")

    def test_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            read_file(self.tmp.name, "nope.txt")


if __name__ == "__main__":
    unittest.main()
