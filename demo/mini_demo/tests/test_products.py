import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from products import find_product


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, price INTEGER, sku TEXT)")
        self.conn.executemany("INSERT INTO products (name, price, sku) VALUES (?, ?, ?)",
                              [("Notebook (fake)", 5, "NB-1"), ("Pen (fake)", 2, "PN-7")])

    def test_found(self):
        self.assertEqual(find_product(self.conn, "PN-7"), (2, "Pen (fake)", 2))

    def test_not_found(self):
        self.assertIsNone(find_product(self.conn, "XX-0"))


if __name__ == "__main__":
    unittest.main()
