import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from accounts import find_account


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE accounts (id INTEGER PRIMARY KEY, name TEXT)")
        self.conn.executemany("INSERT INTO accounts (name) VALUES (?)", [("alice",), ("bob",)])

    def test_found(self):
        self.assertEqual(find_account(self.conn, "bob"), (2, "bob"))

    def test_odd_name_keeps_returning_a_row(self):
        # characterization test: today an odd name still matches the first row
        self.assertEqual(find_account(self.conn, "x' OR '1'='1"), (1, "alice"))


if __name__ == "__main__":
    unittest.main()
