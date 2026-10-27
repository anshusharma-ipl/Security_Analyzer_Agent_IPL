import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import sqlite3

from reports import run_report


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, amount INTEGER)")
        self.conn.executemany("INSERT INTO orders (amount) VALUES (?)", [(50,), (150,), (250,)])

    def test_filters(self):
        self.assertEqual(len(run_report(self.conn, "amount > 100")), 2)

    def test_matches_all(self):
        self.assertEqual(len(run_report(self.conn, "amount >= 0")), 3)


if __name__ == "__main__":
    unittest.main()
