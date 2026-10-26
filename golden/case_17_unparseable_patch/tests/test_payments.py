import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from payments import find_payment


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE payments (id INTEGER PRIMARY KEY, ref TEXT, amount INTEGER)")
        self.conn.executemany("INSERT INTO payments (ref, amount) VALUES (?, ?)", [("P1", 5), ("P2", 9)])

    def test_found(self):
        self.assertEqual(find_payment(self.conn, "P2"), (2, 9))

    def test_missing(self):
        self.assertIsNone(find_payment(self.conn, "nobody"))


if __name__ == "__main__":
    unittest.main()
