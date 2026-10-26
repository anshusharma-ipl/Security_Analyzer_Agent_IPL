import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from people import find_person


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE people (id INTEGER PRIMARY KEY, name TEXT)")
        self.conn.executemany("INSERT INTO people (name) VALUES (?)", [("ann",), ("ben",)])

    def test_found(self):
        self.assertEqual(find_person(self.conn, "ben"), (2,))

    def test_missing(self):
        self.assertIsNone(find_person(self.conn, "nobody"))


if __name__ == "__main__":
    unittest.main()
