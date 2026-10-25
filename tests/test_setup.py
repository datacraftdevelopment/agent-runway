import json
import os
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from runway import db, setup


class SetupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ['RUNWAY_HOME'] = str(self.root / 'home')

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def test_a_version_1_database_gains_check_cmd(self):
        path = self.root / 'home' / 'runway.db'
        path.parent.mkdir(parents=True)
        con = sqlite3.connect(str(path), isolation_level=None)
        con.executescript('BEGIN;\n' + db.MIGRATIONS[1] + "\nINSERT INTO meta VALUES ('schema_version', '1');\n"
                          "INSERT INTO repos(name, path) VALUES ('old', '/tmp/old');\nCOMMIT;")
        con.close()
        con = db.connect()
        self.assertEqual(db.meta(con, 'schema_version'), str(db.SCHEMA_VERSION))
        self.assertIsNone(db.repo(con, 'old')['check_cmd'])
        con.close()

    def test_suggest_check(self):
        cases = {
            'runway.json': (json.dumps({'check_cmd': 'make ci'}), 'make ci'),
            'package.json': (json.dumps({'scripts': {'test': 'jest'}}), 'npm test'),
            'Package.swift': ('// swift', 'swift test'),
            'Cargo.toml': ('[package]', 'cargo test'),
        }
        for name, (text, want) in cases.items():
            d = self.root / name.replace('.', '-')
            d.mkdir()
            (d / name).write_text(text)
            self.assertEqual(setup.suggest_check(d), want, name)
        py = self.root / 'py'
        (py / 'tests').mkdir(parents=True)
        (py / 'tests' / 'test_x.py').write_text('')
        self.assertEqual(setup.suggest_check(py), 'python3 -m unittest -q')
        empty = self.root / 'empty'
        empty.mkdir()
        self.assertIsNone(setup.suggest_check(empty))

    def test_install_command_links_once_and_never_replaces(self):
        bin_dir = self.root / 'bin'
        with mock.patch.object(setup, 'link_dir_on_path', return_value=True):
            msg = setup.install_command(bin_dir)
            link = bin_dir / 'runway'
            self.assertTrue(link.is_symlink())
            self.assertEqual(link.resolve(), setup.own_command().resolve())
            self.assertIn('linked', msg)
            self.assertIn('already points', setup.install_command(bin_dir))
            link.unlink()
            link.write_text('someone else')
            with self.assertRaisesRegex(db.RunwayError, 'already exists'):
                setup.install_command(bin_dir)
            self.assertEqual(link.read_text(), 'someone else')

    def test_install_command_says_when_the_folder_is_not_on_path(self):
        with mock.patch.object(setup, 'link_dir_on_path', return_value=False):
            self.assertIn('add', setup.install_command(self.root / 'elsewhere'))

    def test_report_records_signins_and_shows_fixes(self):
        con = db.connect()
        found = {'git', 'gh', 'tmux', 'claude'}           # codex missing

        def shell(cmd, timeout=60):
            name = cmd.split()[-1]
            if cmd.startswith('command -v'):
                ok = name in found
                return subprocess.CompletedProcess(cmd, 0 if ok else 1, f'/usr/local/bin/{name}\n' if ok else '', '')
            if cmd == 'echo "$PATH"':
                return subprocess.CompletedProcess(cmd, 0, '/usr/bin', '')
            if cmd == 'claude auth status':
                return subprocess.CompletedProcess(cmd, 0, '{"loggedIn": true}', '')
            return subprocess.CompletedProcess(cmd, 1, '', 'not logged in')   # gh auth status
        with mock.patch.object(setup, 'login_shell', side_effect=shell):
            rep = setup.report(con)
        tools = {t['name']: t for t in rep['tools']}
        self.assertEqual(tools['codex']['fix'], 'npm install -g @openai/codex')
        self.assertIsNone(tools['git']['fix'])
        signins = {s['name']: s for s in rep['signins']}
        self.assertTrue(signins['claude']['ok'])
        # One engine is enough: the missing one is optional, not a failure.
        self.assertTrue(tools['codex']['optional'])
        self.assertTrue(signins['codex']['optional'])
        self.assertEqual(signins['github']['fix'], 'gh auth login')
        self.assertFalse(signins['github']['optional'])
        self.assertEqual(rep['engines'], ['claude'])
        self.assertFalse(rep['ready'])                      # GitHub isn't signed in
        self.assertTrue(rep['skills']['built'])        # this checkout carries plugin/
        self.assertFalse(rep['skills']['codex'])       # codex isn't installed in this fake Mac
        row = con.execute("SELECT claude, codex, github FROM setup WHERE runner='This Mac'").fetchone()
        self.assertEqual(tuple(row), ('yes', 'optional', 'sign_in'))
        agents = dict(con.execute('SELECT kind, signed_in FROM agents').fetchall())
        self.assertEqual(agents, {'claude': 1, 'codex': 0})
        con.close()


STUB = {
    'claude': 'if [ "$1 $2" = "auth status" ]; then echo \'{"loggedIn": true}\'; fi\nexit 0\n',
    'codex': 'exit 0\n',
    'gh': 'exit 0\n',
    'tmux': 'exit 0\n',
}


class DoctorOneEngineTest(unittest.TestCase):
    """The real runway doctor, in a temp HOME whose login shell sees only stub tools: one engine is a full green."""

    def run_doctor(self, engines):
        with tempfile.TemporaryDirectory() as tmp:
            home, stubs = Path(tmp) / 'home', Path(tmp) / 'stubs'
            home.mkdir()
            stubs.mkdir()
            for name, body in STUB.items():
                if name in ('claude', 'codex') and name not in engines:
                    continue                                 # the missing engine is simply not on PATH
                (stubs / name).write_text('#!/bin/sh\n' + body)
                (stubs / name).chmod(0o755)
            (home / '.zprofile').write_text(f'export PATH="{stubs}:/usr/bin:/bin:/usr/sbin:/sbin"\n')
            env = {'HOME': str(home), 'SHELL': '/bin/zsh', 'PATH': '/usr/bin:/bin',
                   'RUNWAY_HOME': str(Path(tmp) / 'runway')}
            cli = Path(__file__).resolve().parent.parent / 'bin' / 'runway'
            res = subprocess.run(['/usr/bin/python3', str(cli), 'doctor', '--json'], env=env,
                                 capture_output=True, text=True, timeout=120)
            plain = subprocess.run(['/usr/bin/python3', str(cli), 'doctor'], env=env, capture_output=True, text=True,
                                   timeout=120)
            return res.returncode, json.loads(res.stdout), plain

    def check(self, engine, missing):
        code, rep, plain = self.run_doctor({engine})
        self.assertEqual(code, 0)
        self.assertTrue(rep['ready'])
        self.assertEqual(rep['engines'], [engine])
        tools = {t['name']: t for t in rep['tools']}
        self.assertFalse(tools[missing]['ok'])
        self.assertTrue(tools[missing]['optional'])
        signins = {s['name']: s for s in rep['signins']}
        self.assertTrue(signins[missing]['optional'])
        self.assertEqual(plain.returncode, 0)
        self.assertIn('(optional: one engine is enough)', plain.stdout)
        self.assertNotIn('NO ', plain.stdout)

    def test_claude_only(self):
        self.check('claude', 'codex')

    def test_codex_only(self):
        self.check('codex', 'claude')

    def test_no_engine_is_not_ready(self):
        code, rep, plain = self.run_doctor(set())
        self.assertEqual(code, 1)
        self.assertFalse(rep['ready'])
        self.assertIn('Runway needs Claude Code or Codex (either one)', plain.stdout)


class FirstRunInitTest(unittest.TestCase):
    """Before "Set it up", doctor checks without making ~/.runway; runway init makes it."""

    def test_doctor_looks_and_init_makes_the_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp) / 'runway'
            env = {**os.environ, 'RUNWAY_HOME': str(home), 'SHELL': '/bin/sh'}
            cli = Path(__file__).resolve().parent.parent / 'bin' / 'runway'
            run = lambda *args: subprocess.run(['/usr/bin/python3', str(cli), *args], env=env, capture_output=True,
                                               text=True, timeout=120)
            rep = json.loads(run('doctor', '--json').stdout)
            self.assertFalse(rep['database_exists'])
            self.assertFalse(home.exists())
            res = run('init')
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertIn(str(home / 'runway.db'), res.stdout)
            self.assertTrue((home / 'runway.db').exists())
            self.assertTrue(json.loads(run('doctor', '--json').stdout)['database_exists'])
            self.assertEqual(run('init').returncode, 0)


class RepoAddTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ['RUNWAY_HOME'] = str(self.root / 'home')

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def clone(self, name, origin):
        path = self.root / name
        subprocess.run(['git', 'init', '-q', str(path)], check=True)
        if origin:
            subprocess.run(['git', '-C', str(path), 'remote', 'add', 'origin', origin], check=True)
        (path / 'tests').mkdir()
        (path / 'tests' / 'test_a.py').write_text('')
        return path

    def test_add_guesses_the_check_or_takes_one(self):
        from runway.cli import main
        path = self.clone('app', 'https://github.com/someone/app.git')
        self.assertEqual(main(['repo', 'add', str(path)]), 0)
        con = db.connect()
        self.assertEqual(db.repo(con, 'app')['check_cmd'], 'python3 -m unittest -q')
        con.close()
        self.assertEqual(main(['repo', 'add', str(path), '--check', 'make test']), 0)
        con = db.connect()
        self.assertEqual(db.repo(con, 'app')['check_cmd'], 'make test')
        con.close()

    def test_refuses_a_clone_without_github(self):
        from runway.cli import main
        self.assertEqual(main(['repo', 'add', str(self.clone('local', None))]), 1)

    def test_the_loop_uses_the_stored_check(self):
        from runway.loop import check_command
        con = db.connect()
        con.execute("INSERT INTO repos(name, path, check_cmd) VALUES ('r', '/tmp/r', 'make test')")
        repo = db.repo(con, 'r')
        self.assertEqual(check_command(repo, {}), 'make test')
        self.assertEqual(check_command(repo, {'check_cmd': 'npm test'}), 'npm test')
        con.close()


if __name__ == '__main__':
    unittest.main()
