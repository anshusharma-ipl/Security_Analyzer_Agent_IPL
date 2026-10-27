import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import sqlite3
import tempfile

from views import handle_search, handle_product, handle_file


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        self.conn.executemany("INSERT INTO users (name) VALUES (?)", [("alice",), ("bob",)])
        self.conn.execute("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, price INTEGER, sku TEXT)")
        self.conn.executemany(
            "INSERT INTO products (name, price, sku) VALUES (?, ?, ?)",
            [("Widget", 999, "WGT-01")],
        )
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        with open(os.path.join(self.tmp.name, "info.txt"), "w") as f:
            f.write("shop info")

    def test_search_one_match(self):
        self.assertEqual(handle_search(self.conn, {"name": "alice"}), ["alice"])

    def test_search_no_name(self):
        self.assertEqual(handle_search(self.conn, {}), [])

    def test_product_found(self):
        self.assertEqual(handle_product(self.conn, {"sku": "WGT-01"}), (1, "Widget", 999))

    def test_product_not_found(self):
        self.assertIsNone(handle_product(self.conn, {"sku": "NOPE"}))

    def test_file_read(self):
        import views as v
        orig = v.BASE_DIR
        v.BASE_DIR = self.tmp.name
        try:
            self.assertEqual(handle_file({"name": "info.txt"}), "shop info")
        finally:
            v.BASE_DIR = orig


if __name__ == "__main__":
    unittest.main()
