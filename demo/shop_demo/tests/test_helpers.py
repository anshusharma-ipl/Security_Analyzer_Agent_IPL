import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from helpers import format_price, paginate


class Tests(unittest.TestCase):
    def test_format_price(self):
        self.assertEqual(format_price(999), "$9.99")

    def test_format_price_zero(self):
        self.assertEqual(format_price(0), "$0.00")

    def test_paginate_first(self):
        items = list(range(25))
        self.assertEqual(paginate(items, 1, 10), list(range(10)))

    def test_paginate_last(self):
        items = list(range(25))
        self.assertEqual(paginate(items, 3, 10), list(range(20, 25)))


if __name__ == "__main__":
    unittest.main()
