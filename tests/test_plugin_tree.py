"""The pm-runway plugin as shipped: manifests, skills, and the public-repo rules."""

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / 'pm-runway'
OURS = ('to-spec', 'to-tickets', 'implement-spec', 'work-ticket', 'review-ticket', 'runway-ask')


class PluginTreeTest(unittest.TestCase):
    def test_manifests(self):
        manifest = json.loads((PLUGIN / '.claude-plugin/plugin.json').read_text())
        self.assertEqual(manifest['name'], 'pm-runway')
        self.assertRegex(manifest['version'], r'^\d+\.\d+\.\d+$')
        market = json.loads((ROOT / '.claude-plugin/marketplace.json').read_text())
        self.assertEqual([(p['name'], p['source']) for p in market['plugins']], [('pm-runway', './pm-runway')])
        json.loads((PLUGIN / 'hooks/hooks.json').read_text())

    def test_every_skill_has_frontmatter_named_after_its_folder(self):
        skills = sorted(p.parent for p in PLUGIN.glob('skills/*/SKILL.md'))
        self.assertGreater(len(skills), 30)
        for d in skills:
            text = (d / 'SKILL.md').read_text()
            m = re.match(r'---\n(.*?)\n---\n', text, re.S)
            self.assertTrue(m, d.name)
            self.assertIn(f'name: {d.name}\n', m.group(1) + '\n', d.name)
            self.assertIn('description:', m.group(1), d.name)
        for name in OURS + ('tdd', 'code-review', 'wayfinder', 'whats-next', 'brainstorming'):
            self.assertTrue((PLUGIN / 'skills' / name / 'SKILL.md').exists(), name)

    def test_no_pm_sp_namespace_left(self):
        for p in PLUGIN.rglob('*'):
            if p.is_file() and p.suffix in ('.md', '.json', '.py', '.sh', '.js', '.html', ''):
                text = p.read_text(errors='ignore')
                self.assertNotRegex(text, r'pm-sp:[a-z]', p)  # a skill or command in pm-sp's namespace

    def test_public_repo_rules(self):
        for p in list(PLUGIN.rglob('*')) + list((ROOT / 'setup').rglob('*')) + [ROOT / 'SETUP.html', ROOT / 'SETUP-AGENT.md']:
            self.assertFalse(p.is_symlink(), p)
            if p.is_file() and p.suffix in ('.md', '.json', '.py', '.sh', '.html', '.yml'):
                text = p.read_text(errors='ignore')
                self.assertNotRegex(text, r'/Users/(?!\.\.\.)[a-z]', p)
                self.assertNotIn('Joe-M6', text, p)
                self.assertNotIn('mini-m4', text, p)

    def test_worker_templates_name_skills_that_exist(self):
        for t in (PLUGIN / 'templates/runway').glob('*.md'):
            for skill in re.findall(r'the ([a-z-]+) skill', t.read_text()):
                self.assertTrue((PLUGIN / 'skills' / skill).exists(), f'{t.name}: {skill}')

    def test_codex_link_script_names_skills_that_exist(self):
        script = (ROOT / 'setup/link-codex-skills.sh').read_text()
        names = re.search(r'for s in ([a-z -]+); do', script).group(1).split()
        for name in names:
            self.assertTrue((PLUGIN / 'skills' / name).exists(), name)

    def test_practice_chunk_is_ready(self):
        import sys
        sys.path.insert(0, str(PLUGIN))
        from runway import tickets as tk
        self.assertEqual(tk.check_all(tk.load_dir(ROOT / 'setup/practice/docs/maps/practice/tickets')), {})


if __name__ == '__main__':
    unittest.main()
