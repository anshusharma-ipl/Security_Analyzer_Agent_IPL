import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import sqlite3

from lookup import find_email


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, email TEXT)")
        self.conn.execute("INSERT INTO accounts (email) VALUES ('a@example.test')")

    def test_found(self):
        self.assertEqual(find_email(self.conn, "a@example.test"), (1,))

    def test_not_found(self):
        self.assertIsNone(find_email(self.conn, "z@example.test"))


if __name__ == "__main__":
    unittest.main()
