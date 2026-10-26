import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTES = ROOT / 'app' / 'release-notes'


def front(text):
    m = re.match(r'---\n(.*?)\n---\n', text, re.S)
    meta = dict(line.split(':', 1) for line in m.group(1).splitlines() if ':' in line) if m else {}
    return {k.strip(): v.strip() for k, v in meta.items()}, text[m.end():] if m else text


class ReleaseNotesRuleTest(unittest.TestCase):
    """The plugin's current version is declared (plugin: x.y.z) by the notes of the release that shipped it, and those
    notes put the skills first: the person needs to know their skills changed before anything else (Joe, 26 Oct)."""

    def test_the_plugin_version_is_announced_first(self):
        version = json.loads((ROOT / 'plugin/agent-runway/.claude-plugin/plugin.json').read_text())['version']
        declaring = [f for f in sorted(NOTES.glob('*.md')) if front(f.read_text())[0].get('plugin') == version]
        self.assertTrue(declaring, f'no release notes declare plugin: {version}; add it to the release that ships it')
        meta, body = front(declaring[-1].read_text())
        first = body.strip().split('\n### ')[0]
        self.assertIn('skills', first.lower(), f'{declaring[-1].name} must talk about the skills in its first section')

    def test_do_this_after_updating_comes_first_when_present(self):
        for f in NOTES.glob('*.md'):
            body = front(f.read_text())[1]
            if '### Do this after updating' in body:
                self.assertTrue(body.strip().startswith('### Do this after updating'), f.name)


if __name__ == '__main__':
    unittest.main()
