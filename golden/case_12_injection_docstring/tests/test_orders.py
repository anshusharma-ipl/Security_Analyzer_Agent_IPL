import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from orders import find_order


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, ref TEXT, total INTEGER)")
        self.conn.executemany("INSERT INTO orders (ref, total) VALUES (?, ?)", [("A1", 10), ("B2", 20)])

    def test_found(self):
        self.assertEqual(find_order(self.conn, "A1"), (1, 10))

    def test_missing(self):
        self.assertIsNone(find_order(self.conn, "nobody"))


if __name__ == "__main__":
    unittest.main()
