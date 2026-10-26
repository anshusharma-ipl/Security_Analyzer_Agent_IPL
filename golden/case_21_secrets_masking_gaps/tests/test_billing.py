import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from billing import find_invoice


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE invoices (id INTEGER PRIMARY KEY, ref TEXT)")
        self.conn.executemany("INSERT INTO invoices (ref) VALUES (?)", [("I1",), ("I2",)])

    def test_found(self):
        self.assertEqual(find_invoice(self.conn, "I2"), (2,))

    def test_missing(self):
        self.assertIsNone(find_invoice(self.conn, "nobody"))


if __name__ == "__main__":
    unittest.main()
