import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from safe_lookup import find_by_email


class Tests(unittest.TestCase):
    def test_found_and_missing(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, email TEXT)")
        conn.execute("INSERT INTO customers (email) VALUES ('a@example.test')")
        self.assertEqual(find_by_email(conn, "a@example.test"), (1,))
        self.assertIsNone(find_by_email(conn, "nobody@example.test"))


if __name__ == "__main__":
    unittest.main()
