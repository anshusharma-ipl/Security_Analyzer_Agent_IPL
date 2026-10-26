import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import sqlite3

from orders import count_orders


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE orders (customer TEXT)")
        self.conn.executemany("INSERT INTO orders VALUES (?)", [("a",), ("a",), ("b",)])

    def test_two_orders(self):
        self.assertEqual(count_orders(self.conn, "a"), 2)

    def test_no_orders(self):
        self.assertEqual(count_orders(self.conn, "z"), 0)


if __name__ == "__main__":
    unittest.main()
