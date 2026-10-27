import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import sqlite3

from views import handle_search


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        self.conn.executemany("INSERT INTO users (name) VALUES (?)", [("alice",), ("bob",)])

    def test_one_match(self):
        self.assertEqual(handle_search(self.conn, {"name": "alice"}), ["alice"])

    def test_no_name(self):
        self.assertEqual(handle_search(self.conn, {}), [])


if __name__ == "__main__":
    unittest.main()
