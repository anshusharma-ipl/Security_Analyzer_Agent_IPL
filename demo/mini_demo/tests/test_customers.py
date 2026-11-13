import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from customers import find_customer


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
        self.conn.executemany("INSERT INTO customers (name, email) VALUES (?, ?)",
                              [("Asha (fake)", "asha@example.test"), ("Ben (fake)", "ben@example.test")])

    def test_found(self):
        self.assertEqual(find_customer(self.conn, "ben@example.test"), (2, "Ben (fake)"))

    def test_not_found(self):
        self.assertIsNone(find_customer(self.conn, "nobody@example.test"))


if __name__ == "__main__":
    unittest.main()
