import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
import sqlite3

from helpers import total_by_region


class Tests(unittest.TestCase):
    def setUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.execute("CREATE TABLE sales (region TEXT, amount INTEGER)")
        self.conn.executemany("INSERT INTO sales VALUES (?, ?)", [("north", 100), ("north", 50), ("south", 200)])

    def test_north(self):
        self.assertEqual(total_by_region(self.conn, "north"), 150)

    def test_south(self):
        self.assertEqual(total_by_region(self.conn, "south"), 200)


if __name__ == "__main__":
    unittest.main()
