import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from archive import archive_name


class Tests(unittest.TestCase):
    def test_returns_zero(self):
        self.assertEqual(archive_name("photos"), 0)


if __name__ == "__main__":
    unittest.main()
