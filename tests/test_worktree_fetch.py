import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from runway.runner import LocalRunner


def sh(*args, cwd):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


class FirstBuildFetchTest(unittest.TestCase):
    """A first build names a branch GitHub doesn't have yet: the worktree must still start from the newest base."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        os.environ['RUNWAY_HOME'] = str(root / 'home')
        origin = root / 'origin.git'
        sh('init', '--quiet', '--bare', '-b', 'main', str(origin), cwd=root)
        self.seed = root / 'seed'
        sh('clone', '--quiet', str(origin), str(self.seed), cwd=root)
        self.commit('first')
        self.clone = root / 'clone'
        sh('clone', '--quiet', str(origin), str(self.clone), cwd=root)
        self.newest = self.commit('second')        # pushed after the clone: its origin/main is now stale

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def commit(self, text):
        (self.seed / 'f.txt').write_text(text)
        sh('add', '-A', cwd=self.seed)
        sh('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '--quiet', '-m', text, cwd=self.seed)
        sh('push', '--quiet', 'origin', 'main', cwd=self.seed)
        return sh('rev-parse', 'HEAD', cwd=self.seed)

    def test_first_build_starts_from_the_newest_base(self):
        repo = {'name': 'app', 'path': str(self.clone), 'base': 'main'}
        wt = LocalRunner().worktree(repo, 'T-1', 1, 'origin/main', branch='rw/T-1')
        self.assertEqual(sh('rev-parse', 'HEAD', cwd=wt), self.newest)
        self.assertEqual((Path(wt) / 'f.txt').read_text(), 'second')


if __name__ == '__main__':
    unittest.main()
