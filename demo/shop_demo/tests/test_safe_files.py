import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from safe_files import read_inside


class Tests(unittest.TestCase):
    def test_reads_inside_and_refuses_outside(self):
        with tempfile.TemporaryDirectory() as tmp:
            with open(os.path.join(tmp, "a.txt"), "w") as handle:
                handle.write("hi")
            self.assertEqual(read_inside(tmp, "a.txt"), "hi")
            with self.assertRaises(ValueError):
                read_inside(tmp, os.path.join("..", "x"))


if __name__ == "__main__":
    unittest.main()
