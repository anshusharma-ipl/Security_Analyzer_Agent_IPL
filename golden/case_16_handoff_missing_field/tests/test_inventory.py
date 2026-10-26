import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from inventory import find_item


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, sku TEXT, qty INTEGER)")
        self.conn.executemany("INSERT INTO items (sku, qty) VALUES (?, ?)", [("K1", 5), ("K2", 7)])

    def test_found(self):
        self.assertEqual(find_item(self.conn, "K2"), (2, 7))

    def test_missing(self):
        self.assertIsNone(find_item(self.conn, "nobody"))


if __name__ == "__main__":
    unittest.main()
