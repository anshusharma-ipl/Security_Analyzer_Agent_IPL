import os
import sqlite3
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from lookup import find_admin, find_user


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)")
        self.conn.execute("CREATE TABLE admins (id INTEGER PRIMARY KEY, name TEXT)")
        self.conn.execute("INSERT INTO users (name) VALUES ('alice')")
        self.conn.execute("INSERT INTO admins (name) VALUES ('root')")

    def test_user(self):
        self.assertEqual(find_user(self.conn, "alice"), (1,))

    def test_admin(self):
        self.assertEqual(find_admin(self.conn, "root"), (1,))


if __name__ == "__main__":
    unittest.main()
