import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from reports import run_report


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, amount INTEGER)")
        self.conn.executemany("INSERT INTO orders (amount) VALUES (?)", [(50,), (150,), (300,)])

    def test_condition_is_applied(self):
        self.assertEqual(run_report(self.conn, "amount > 100"), [(2, 150), (3, 300)])

    def test_empty_result(self):
        self.assertEqual(run_report(self.conn, "amount > 1000"), [])


if __name__ == "__main__":
    unittest.main()
