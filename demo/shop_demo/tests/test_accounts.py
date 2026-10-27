import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from accounts import check_password, hash_password


class Tests(unittest.TestCase):
    def test_round_trip(self):
        self.assertTrue(check_password("secret", hash_password("secret")))

    def test_wrong_password(self):
        self.assertFalse(check_password("nope", hash_password("secret")))


if __name__ == "__main__":
    unittest.main()
