import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import sqlite3

from users import find_user


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        self.conn.executemany("INSERT INTO users (name) VALUES (?)", [("alice",), ("bob",)])

    def test_found(self):
        self.assertEqual(find_user(self.conn, "alice"), (1, "alice"))

    def test_not_found(self):
        self.assertIsNone(find_user(self.conn, "carol"))


if __name__ == "__main__":
    unittest.main()
