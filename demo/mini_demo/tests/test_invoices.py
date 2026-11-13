import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from invoices import find_invoice


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY, customer_id TEXT, status TEXT, total INTEGER)")
        self.conn.executemany("INSERT INTO invoices (customer_id, status, total) VALUES (?, ?, ?)",
                              [("c1", "paid", 120), ("c1", "open", 80), ("c2", "paid", 45)])

    def test_found(self):
        self.assertEqual(find_invoice(self.conn, "c1", "open"), (2, 80))

    def test_not_found(self):
        self.assertIsNone(find_invoice(self.conn, "c2", "open"))


if __name__ == "__main__":
    unittest.main()
