import json
import os
import sqlite3
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

from runway import db, setup

CLAUDE_LIST = """Installed plugins:

  ❯ agent-runway@agent-runway
    Version: 0.2.0
    Read from: /Applications/Runway.app/Contents/Resources/cli/plugin/agent-runway
    Scope: user
    Status: ✔ enabled

  ❯ other@somewhere
    Version: 9.9.9
"""
CODEX_LIST = """Marketplace `agent-runway`
/Applications/Runway.app/Contents/Resources/cli/plugin/.claude-plugin/marketplace.json

PLUGIN                     STATUS              VERSION  SOURCE
agent-runway@agent-runway  installed, enabled  0.2.0    /Applications/Runway.app/Contents/Resources/cli/plugin/agent-runway
"""

# Stub agents for a temp HOME: each keeps the installed version in a file and logs every command it was given.
STUB = r'''#!/bin/sh
name=$(basename "$0")
state="$HOME/$name-version"
echo "$name $*" >> "$HOME/calls"
case "$1 $2" in
  "plugin list")
    [ -f "$state" ] || exit 0
    if [ "$name" = claude ]; then printf '  ❯ agent-runway@agent-runway\n    Version: %s\n' "$(cat "$state")"
    else printf 'agent-runway@agent-runway  installed, enabled  %s    /x\n' "$(cat "$state")"; fi ;;
  "plugin install"|"plugin add"|"plugin update") cat "$BUNDLED" > "$state" ;;
  "plugin remove") rm -f "$state" ;;
esac
exit 0
'''


class VersionTest(unittest.TestCase):
    def test_reads_each_agents_list(self):
        self.assertEqual(setup.installed_version('claude', CLAUDE_LIST), '0.2.0')
        self.assertEqual(setup.installed_version('codex', CODEX_LIST), '0.2.0')
        self.assertIsNone(setup.installed_version('claude', 'no plugins'))
        self.assertEqual(setup.installed_version('codex', 'agent-runway@agent-runway  installed'), 'unknown')

    def test_older(self):
        self.assertTrue(setup.older('0.2.0', '0.2.1'))
        self.assertTrue(setup.older('0.9.0', '0.10.0'))
        self.assertFalse(setup.older('0.2.1', '0.2.1'))
        self.assertFalse(setup.older('0.3.0', '0.2.1'))       # newer than the app's: leave it
        self.assertFalse(setup.older('unknown', '0.2.1'))       # can't tell: leave it
        self.assertFalse(setup.older(None, '0.2.1'))           # not installed is not "older"

    def test_bundled_version_is_the_plugins(self):
        manifest = json.loads((setup.plugin_dir() / 'agent-runway/.claude-plugin/plugin.json').read_text())
        self.assertEqual(setup.bundled_version(), manifest['version'])


class UpdateTest(unittest.TestCase):
    """runway doctor and install-skills in a temp HOME whose claude and codex are stubs."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / 'home'
        stubs = Path(self.tmp.name) / 'stubs'
        self.home.mkdir()
        stubs.mkdir()
        for name in ('claude', 'codex', 'gh', 'tmux'):
            (stubs / name).write_text(STUB)
            (stubs / name).chmod(0o755)
        (self.home / '.zprofile').write_text(f'export PATH="{stubs}:/usr/bin:/bin:/usr/sbin:/sbin"\n')
        self.bundled = Path(self.tmp.name) / 'bundled'
        self.bundled.write_text(setup.bundled_version())
        self.env = {'HOME': str(self.home), 'SHELL': '/bin/zsh', 'PATH': '/usr/bin:/bin',
                    'RUNWAY_HOME': str(Path(self.tmp.name) / 'runway'), 'BUNDLED': str(self.bundled)}

    def tearDown(self):
        self.tmp.cleanup()

    def runway(self, *args):
        cli = Path(__file__).resolve().parent.parent / 'bin' / 'runway'
        return subprocess.run(['/usr/bin/python3', str(cli), *args], env=self.env, capture_output=True, text=True,
                              timeout=120)

    def calls(self):
        p = self.home / 'calls'
        lines = p.read_text().splitlines() if p.exists() else []
        p.unlink(missing_ok=True)
        return [l for l in lines if 'plugin list' not in l and 'auth' not in l and 'login' not in l]

    def test_an_older_install_is_flagged_and_updated(self):
        for agent in ('claude', 'codex'):
            (self.home / f'{agent}-version').write_text('0.0.1')
        skills = json.loads(self.runway('doctor', '--json').stdout)['skills']
        self.assertTrue(skills['outdated'])
        self.assertTrue(skills['installed'])
        self.assertEqual((skills['claude_version'], skills['codex_version'], skills['version']),
                         ('0.0.1', '0.0.1', setup.bundled_version()))
        self.assertIn('older', skills['note'])
        self.calls()
        res = self.runway('install-skills')
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn(f'claude: updated agent-runway from 0.0.1 to {setup.bundled_version()}', res.stdout)
        made = self.calls()
        self.assertIn('claude plugin marketplace update agent-runway', made)
        self.assertIn('claude plugin update agent-runway@agent-runway', made)
        self.assertNotIn('claude plugin install agent-runway@agent-runway', made)
        self.assertIn('codex plugin remove agent-runway@agent-runway', made)
        self.assertIn('codex plugin add agent-runway@agent-runway', made)
        skills = json.loads(self.runway('doctor', '--json').stdout)['skills']
        self.assertFalse(skills['outdated'])
        self.assertEqual(skills['claude_version'], setup.bundled_version())

    def test_claudes_own_record_wins_over_its_list(self):
        """Joe's Mac, 26 Oct: claude plugin list said 0.2.1 (read from the app's folder) while Claude Code ran its
        cached 0.2.0. The record in installed_plugins.json is what's in use."""
        (self.home / 'claude-version').write_text(setup.bundled_version())      # the list says current
        record = self.home / '.claude' / 'plugins'
        record.mkdir(parents=True)
        (record / 'installed_plugins.json').write_text(json.dumps({'version': 2, 'plugins': {
            'agent-runway@agent-runway': [{'scope': 'user', 'version': '0.0.1', 'installPath': '/x/0.0.1'}]}}))
        skills = json.loads(self.runway('doctor', '--json').stdout)['skills']
        self.assertEqual((skills['claude_version'], skills['outdated']), ('0.0.1', True))

    def test_update_only_updates_whats_older_and_adds_nothing(self):
        (self.home / 'claude-version').write_text('0.0.1')                     # Claude Code has an old one
        self.calls()                                                            # Codex has none
        res = self.runway('install-skills', '--update-only')
        self.assertEqual(res.returncode, 0, res.stderr)
        made = self.calls()
        self.assertIn('claude plugin update agent-runway@agent-runway', made)
        self.assertFalse(any(c.startswith('codex plugin add') for c in made))  # never added to a new engine
        self.assertIn('codex: agent-runway not installed, left alone', res.stdout)
        res = self.runway('install-skills', '--update-only')                     # now current: nothing to do
        self.assertIn(f'claude: agent-runway {setup.bundled_version()} is current', res.stdout)
        self.assertNotIn('claude plugin update agent-runway@agent-runway', self.calls())

    def test_a_fresh_install_installs_and_a_current_one_is_left_alone(self):
        self.assertFalse(json.loads(self.runway('doctor', '--json').stdout)['skills']['installed'])
        self.calls()
        self.runway('install-skills')
        made = self.calls()
        self.assertIn('claude plugin install agent-runway@agent-runway', made)
        self.assertNotIn('codex plugin remove agent-runway@agent-runway', made)
        skills = json.loads(self.runway('doctor', '--json').stdout)['skills']
        self.assertEqual((skills['installed'], skills['outdated']), (True, False))


class BackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['RUNWAY_HOME'] = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def old_db(self, version):
        """A database left at an older schema, with a ticket in it."""
        path = db.db_path()
        con = sqlite3.connect(str(path))
        for v in range(1, version + 1):
            con.executescript(db.MIGRATIONS[v])
        con.execute("INSERT INTO meta(key, value) VALUES ('schema_version', ?)", (str(version),))
        con.execute("INSERT INTO repos(name, path) VALUES ('app', '/tmp/app')")
        con.execute("INSERT INTO tickets(id, repo, base, title, filed_at, updated_at) "
                    "VALUES ('T-1', 'app', 'main', 'Keep me', 1, 1)")
        con.commit()
        con.close()

    def test_a_migration_backs_the_database_up_first(self):
        self.old_db(3)
        con = db.connect()
        backups = list((db.home() / 'backups').glob('runway-v3-*.db'))
        self.assertEqual(len(backups), 1)
        old = sqlite3.connect(str(backups[0]))
        self.assertEqual(old.execute("SELECT value FROM meta WHERE key='schema_version'").fetchone()[0], '3')
        self.assertEqual(old.execute('SELECT title FROM tickets').fetchall(), [('Keep me',)])
        old.close()
        self.assertEqual(db.ticket(con, 'T-1')['title'], 'Keep me')      # the migrated one still has it
        con.close()
        db.connect().close()                                             # already current: no new backup
        self.assertEqual(len(list((db.home() / 'backups').glob('*.db'))), 1)

    def test_a_new_database_has_nothing_to_back_up_and_only_five_are_kept(self):
        con = db.connect()
        self.assertFalse((db.home() / 'backups').exists())
        for _ in range(7):
            db.back_up(con, 7)
            time.sleep(0.01)
        self.assertEqual(len(list((db.home() / 'backups').glob('runway-v7-*.db'))), db.KEEP_BACKUPS)
        con.close()


if __name__ == '__main__':
    unittest.main()
