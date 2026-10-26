import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from stats import count_active


class Tests(unittest.TestCase):
    def test_count(self):
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, state TEXT)")
        conn.executemany("INSERT INTO users (state) VALUES (?)", [("active",), ("gone",), ("active",)])
        self.assertEqual(count_active(conn), 2)


if __name__ == "__main__":
    unittest.main()
