import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from uploads import save_upload


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def test_saves_inside_the_folder(self):
        target = save_upload(self.tmp.name, "a.txt", b"hello")
        with open(target, "rb") as handle:
            self.assertEqual(handle.read(), b"hello")


if __name__ == "__main__":
    unittest.main()
