import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from runway import db, setup

PLUGIN = Path(__file__).resolve().parent.parent / 'plugin'


def done(cmd, code=0, out=''):
    return subprocess.CompletedProcess(cmd, code, out, '')


class PluginTreeTest(unittest.TestCase):
    """One plugin for both agents: a manifest each, the marketplace, and every skill with its frontmatter."""

    def test_manifests_agree(self):
        market = json.loads((PLUGIN / '.claude-plugin/marketplace.json').read_text())
        claude = json.loads((PLUGIN / 'agent-runway/.claude-plugin/plugin.json').read_text())
        codex = json.loads((PLUGIN / 'agent-runway/.codex-plugin/plugin.json').read_text())
        self.assertEqual(market['name'], setup.PLUGIN)
        self.assertEqual([p['name'] for p in market['plugins']], [setup.PLUGIN])
        self.assertEqual((claude['name'], codex['name']), (setup.PLUGIN, setup.PLUGIN))
        self.assertEqual(claude['version'], codex['version'])
        self.assertEqual(codex['skills'], './skills/')

    def test_each_skill_has_name_and_description(self):
        names = []
        for skill in sorted((PLUGIN / 'agent-runway/skills').iterdir()):
            text = (skill / 'SKILL.md').read_text()
            self.assertTrue(text.startswith('---\n'), skill.name)
            front = text.split('---\n')[1]
            self.assertIn(f'name: {skill.name}\n', front)
            self.assertIn('description: ', front)
            names.append(skill.name)
        self.assertEqual(names, ['file-tickets', 'runway', 'setup', 'take-back'])

    def test_skills_never_chain_commands_in_their_examples(self):
        """A session with an allow-list refuses chained commands, so no bash example chains one."""
        for skill in (PLUGIN / 'agent-runway/skills').iterdir():
            text = (skill / 'SKILL.md').read_text()
            for block in text.split('```bash')[1:]:
                code = block.split('```')[0]
                for line in code.splitlines():
                    cmd = line.split('#')[0]
                    self.assertNotRegex(cmd, r'&&|\|\||;\s*\S', f'{skill.name}: {line}')

    def test_nothing_personal_in_the_plugin(self):
        for path in PLUGIN.rglob('*'):
            if path.is_file():
                text = path.read_text()
                self.assertNotIn('/Users/', text, path)


class SkillsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['RUNWAY_HOME'] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def test_status_reads_each_agents_plugin_list(self):
        def shell(cmd, timeout=60):
            if cmd == 'claude plugin list':
                return done(cmd, 0, '  ❯ agent-runway@agent-runway\n    Status: enabled\n')
            if cmd == 'codex plugin list':
                return done(cmd, 0, 'Marketplace `openai-bundled`\n')
            return done(cmd, 0, '/usr/local/bin/x\n')
        with mock.patch.object(setup, 'login_shell', side_effect=shell):
            st = setup.skills_status()
        self.assertEqual((st['built'], st['claude'], st['codex']), (True, True, False))
        self.assertIn('Not in Codex yet', st['note'])

    def test_install_runs_each_agents_own_commands(self):
        ran = []

        def shell(cmd, timeout=60):
            ran.append(cmd)
            if cmd.endswith('plugin list'):
                return done(cmd, 0, 'agent-runway@agent-runway')
            if 'marketplace add' in cmd and cmd.startswith('codex'):
                return done(cmd, 1, 'marketplace already added')   # a second run is fine
            return done(cmd, 0, '/usr/local/bin/x')
        with mock.patch.object(setup, 'login_shell', side_effect=shell):
            msg = setup.install_skills()
        q = str(PLUGIN)
        self.assertIn(f'claude plugin marketplace add {q}', ran)
        self.assertIn('claude plugin install agent-runway@agent-runway', ran)
        self.assertIn(f'codex plugin marketplace add {q}', ran)
        self.assertIn('codex plugin add agent-runway@agent-runway', ran)
        self.assertIn('claude: installed', msg)
        self.assertIn('codex: installed', msg)

    def test_install_skips_a_missing_agent_and_stops_on_a_real_failure(self):
        def shell(cmd, timeout=60):
            if cmd == 'command -v codex':
                return done(cmd, 1)
            if cmd.startswith('claude plugin install'):
                return done(cmd, 1, 'network down')
            return done(cmd, 0)
        with mock.patch.object(setup, 'login_shell', side_effect=shell):
            with self.assertRaisesRegex(db.RunwayError, 'network down'):
                setup.install_skills()
            self.assertIn('codex: not installed, skipped', setup.install_skills(('codex',)))


class FileBatchAndWhichTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ['RUNWAY_HOME'] = str(self.root / 'home')
        self.clone = self.root / 'notes'
        subprocess.run(['git', 'init', '-q', str(self.clone)], check=True)
        subprocess.run(['git', '-C', str(self.clone), 'remote', 'add', 'origin',
                        'https://github.com/someone/notes.git'], check=True)

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def test_repo_which_and_file_batch(self):
        from runway.cli import main
        self.assertEqual(main(['repo', 'which', str(self.clone)]), 1)   # not watched yet
        self.assertEqual(main(['repo', 'add', str(self.clone), '--check', 'make test']), 0)
        (self.clone / 'sub').mkdir()
        self.assertEqual(main(['repo', 'which', str(self.clone / 'sub')]), 0)
        batch = self.root / 'batch.json'
        batch.write_text(json.dumps({'repo': 'notes', 'tickets': [
            {'title': 'Count', 'risk': 'low', 'risk_reason': 'new function', 'acceptance': ['A1: it counts']}]}))
        self.assertEqual(main(['file', '--batch', str(batch), '--filed-from', 'Codex session']), 0)
        con = db.connect()
        self.assertEqual(db.ticket(con, 'T-1')['filed_from'], 'Codex session')
        con.close()


if __name__ == '__main__':
    unittest.main()
