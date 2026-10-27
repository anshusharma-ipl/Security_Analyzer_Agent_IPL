import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import sqlite3

from products import find_product


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, price INTEGER, sku TEXT)")
        self.conn.executemany(
            "INSERT INTO products (name, price, sku) VALUES (?, ?, ?)",
            [("Widget", 999, "WGT-01"), ("Gadget", 1499, "GDG-02")],
        )

    def test_found(self):
        self.assertEqual(find_product(self.conn, "WGT-01"), (1, "Widget", 999))

    def test_not_found(self):
        self.assertIsNone(find_product(self.conn, "NOPE"))


if __name__ == "__main__":
    unittest.main()
