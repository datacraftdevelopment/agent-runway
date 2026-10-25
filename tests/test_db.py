import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from runway import db


class DbTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['RUNWAY_HOME'] = self.tmp.name
        self.con = db.connect()

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def test_fresh_database_is_seeded(self):
        self.assertEqual(db.meta(self.con, 'schema_version'), str(db.SCHEMA_VERSION))
        runners = [dict(r) for r in self.con.execute('SELECT name, kind, slots FROM runners')]
        self.assertEqual(runners, [{'name': 'This Mac', 'kind': 'this_mac', 'slots': 2}])
        agents = [r['kind'] for r in self.con.execute('SELECT kind FROM agents ORDER BY kind')]
        self.assertEqual(agents, ['claude', 'codex'])

    def test_reconnect_does_not_reseed_or_remigrate(self):
        db.set_meta(self.con, 'next_ticket', 7)
        self.con.close()
        self.con = db.connect()
        self.assertEqual(db.meta(self.con, 'next_ticket'), '7')

    def test_ticket_ids_count_up(self):
        self.assertEqual([db.next_ticket_id(self.con) for _ in range(3)], ['T-1', 'T-2', 'T-3'])

    def test_lives_under_runway_home(self):
        self.assertEqual(db.db_path(), Path(self.tmp.name) / 'runway.db')
        self.assertTrue(db.db_path().exists())


class CliRepoTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['RUNWAY_HOME'] = str(Path(self.tmp.name) / 'home')
        self.clone = Path(self.tmp.name) / 'demo'
        subprocess.run(['git', 'init', '-q', str(self.clone)], check=True)
        subprocess.run(['git', '-C', str(self.clone), 'remote', 'add', 'origin',
                        'git@github.com:someone/demo.git'], check=True)

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def test_repo_add_reads_the_github_slug(self):
        from runway.cli import main
        self.assertEqual(main(['repo', 'add', str(self.clone)]), 0)
        con = db.connect()
        row = db.repo(con, 'demo')
        self.assertEqual((row['slug'], row['base'], row['runs_on']), ('someone/demo', 'main', 'any'))
        con.close()

    def test_repo_add_refuses_a_plain_folder(self):
        from runway.cli import main
        plain = Path(self.tmp.name) / 'plain'
        plain.mkdir()
        self.assertEqual(main(['repo', 'add', str(plain)]), 1)


if __name__ == '__main__':
    unittest.main()
