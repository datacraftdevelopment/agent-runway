import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from runway import db, setup, status
from runway.loop import allowed_commands, check_command


def sh(*args, cwd):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


class RepoChecksTest(unittest.TestCase):
    """A clone whose origin/main has a Swift package one folder down and a tools/ script, no runway.json."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        os.environ['RUNWAY_HOME'] = str(root / 'home')
        os.environ['GIT_TERMINAL_PROMPT'] = '0'                    # a fetch from the made-up origin fails quietly
        self.env = {**os.environ}
        origin = root / 'origin.git'
        sh('init', '--quiet', '--bare', '-b', 'main', str(origin), cwd=root)
        seed = root / 'seed'
        sh('clone', '--quiet', str(origin), str(seed), cwd=root)
        (seed / 'Core').mkdir()
        (seed / 'Core' / 'Package.swift').write_text('// swift-tools-version:5.9\n')
        (seed / 'web').mkdir()
        (seed / 'web' / 'package.json').write_text(json.dumps({'scripts': {'test': 'vitest', 'build': 'vite build'}}))
        (seed / 'README.md').write_text('hi\n')
        sh('add', '-A', cwd=seed)
        sh('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '--quiet', '-m', 'seed', cwd=seed)
        sh('push', '--quiet', 'origin', 'main', cwd=seed)
        self.clone = root / 'clone'
        sh('clone', '--quiet', str(origin), str(self.clone), cwd=root)
        # A GitHub-looking origin (for the slug); origin/main is already here from the clone. Fetches from it fail
        # quietly, as they do offline.
        sh('remote', 'set-url', 'origin', 'https://github.com/someone/app.git', cwd=self.clone)
        self.seed, self.origin = seed, origin

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)
        os.environ.pop('GIT_TERMINAL_PROMPT', None)

    def runway(self, *args):
        cli = Path(__file__).resolve().parent.parent / 'bin' / 'runway'
        return subprocess.run(['/usr/bin/python3', str(cli), *args], env=self.env, capture_output=True, text=True,
                              timeout=120)

    def test_suggests_from_origins_base_one_folder_down(self):
        (self.clone / 'Makefile').write_text('test:\n\ttrue\n')            # only on disk: not what Runway builds
        found = setup.suggest_commands(self.clone, 'origin/main')
        self.assertEqual(found['check'], 'swift test --package-path Core')
        self.assertEqual(found['commands'], ['swift build --package-path Core', 'swift run --package-path Core',
                                             'npm --prefix web test', 'npm --prefix web run build'])
        self.assertIn('make', setup.suggest_commands(self.clone)['commands'])   # the folder on disk does have it

    def test_runway_json_on_the_base_wins(self):
        (self.seed / 'runway.json').write_text(json.dumps({'check_cmd': 'make check', 'worker_commands': ['make']}))
        sh('add', '-A', cwd=self.seed)
        sh('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '--quiet', '-m', 'cfg', cwd=self.seed)
        sh('push', '--quiet', 'origin', 'main', cwd=self.seed)
        sh('fetch', '--quiet', str(self.origin), '+refs/heads/main:refs/remotes/origin/main', cwd=self.clone)
        found = setup.suggest_commands(self.clone, 'origin/main')
        self.assertEqual(found['check'], 'make check')
        self.assertEqual(found['commands'][0], 'make')

    def test_repo_add_keeps_the_commands_in_runway_and_check_changes_them(self):
        res = self.runway('repo', 'add', str(self.clone), '--name', 'app')
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('check: swift test --package-path Core', res.stdout)
        self.assertIn('sessions may also run: swift build --package-path Core', res.stdout)
        con = db.connect()
        r = db.repo(con, 'app')
        self.assertEqual(json.loads(r['worker_commands'])[0], 'swift build --package-path Core')
        # The loop gives sessions these when runway.json says nothing, and runway.json's when it does.
        self.assertEqual(check_command(r, {}), 'swift test --package-path Core')
        self.assertEqual(allowed_commands(r, {})[:1], ['swift build --package-path Core'])
        self.assertEqual(allowed_commands(r, {'worker_commands': ['make']}), ['make'])
        self.assertEqual(check_command(r, {'check_cmd': 'make check'}), 'make check')
        snap = status.snapshot(con)['repos'][0]
        self.assertEqual((snap['check_cmd'], snap['check_from']), ('swift test --package-path Core', 'runway'))
        con.close()
        res = self.runway('repo', 'check', 'app', '--check', 'swift test --package-path Core --parallel',
                          '--allow', 'swift build --package-path Core', '--json')
        self.assertEqual(json.loads(res.stdout), {'repo': 'app', 'check': 'swift test --package-path Core --parallel',
                                                  'commands': ['swift build --package-path Core']})
        res = self.runway('repo', 'check', 'app', '--suggest', '--json')
        self.assertEqual(json.loads(res.stdout)['check'], 'swift test --package-path Core')
        self.runway('repo', 'check', 'app', '--check', '')
        con = db.connect()
        self.assertEqual(status.snapshot(con)['repos'][0]['check_from'], None)        # the board flags it
        con.close()

    def test_suggest_check_endpoint_lists_the_commands(self):
        res = self.runway('repo', 'suggest-check', str(self.clone))
        data = json.loads(res.stdout)
        self.assertEqual(data['check'], 'swift test --package-path Core')
        self.assertIn('npm --prefix web test', data['commands'])


if __name__ == '__main__':
    unittest.main()
