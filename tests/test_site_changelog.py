import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class SiteChangelogTest(unittest.TestCase):
    """site/changelog.html is built from app/release-notes, so it must match them."""

    def test_changelog_page_is_current(self):
        r = subprocess.run([sys.executable, str(ROOT / 'scripts/site_changelog.py'), '--check'],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)


if __name__ == '__main__':
    unittest.main()
