import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from app import handle_customer, handle_report


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT)")
        self.conn.execute("INSERT INTO customers (name, email) VALUES ('Asha (fake)', 'asha@example.test')")
        self.conn.execute("CREATE TABLE orders (id INTEGER PRIMARY KEY, amount INTEGER)")
        self.conn.execute("INSERT INTO orders (amount) VALUES (150)")

    def test_each_handler_reaches_its_lookup(self):
        self.assertEqual(handle_customer(self.conn, {"email": "asha@example.test"}), (1, "Asha (fake)"))
        self.assertEqual(handle_report(self.conn, {"filter": "amount > 100"}), [(1, 150)])


if __name__ == "__main__":
    unittest.main()
