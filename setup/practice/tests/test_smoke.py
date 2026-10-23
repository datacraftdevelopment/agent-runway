import unittest

import tally


class Smoke(unittest.TestCase):
    def test_package_imports(self):
        self.assertTrue(tally.__doc__)
