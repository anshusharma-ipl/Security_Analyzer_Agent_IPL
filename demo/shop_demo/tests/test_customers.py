import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import json
import sqlite3

from customers import find_customer

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "customers.json")


class Tests(unittest.TestCase):
    def setUp(self):
        with open(FIXTURE) as f:
            rows = json.load(f)
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT, phone TEXT)")
        self.conn.executemany("INSERT INTO customers (name, email, phone) VALUES (?, ?, ?)",
                              [(r["name"], r["email"], r["phone"]) for r in rows])

    def test_found(self):
        self.assertEqual(find_customer(self.conn, "asha@example.test"), (1, "Asha Verma (fake)"))

    def test_not_found(self):
        self.assertIsNone(find_customer(self.conn, "nobody@example.test"))


if __name__ == "__main__":
    unittest.main()
