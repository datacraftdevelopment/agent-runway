import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from runway import db, worker
from runway.ssh import SSHRunner, run_folder

# Stands in for ssh: runs the command here, with HOME pointed at the "other Mac's" home. A file named `down` next to
# the script makes it fail as ssh does when it can't connect.
FAKE_SSH = '''#!/bin/sh
here=$(dirname "$0")
while [ "$1" = "-o" ]; do shift 2; done
host=$1; shift
[ -e "$here/down" ] && { echo "ssh: connect to host $host: Connection refused" >&2; exit 255; }
echo "$host" >> "$here/hosts"
HOME="$FAKE_REMOTE_HOME" exec sh -c "$*"
'''

# Stands in for tmux: new-session runs the line at once and the session stays "live" until the test ends it.
FAKE_TMUX = '''#!/bin/sh
here=$(dirname "$0")
live="$here/live"
touch "$live"
case "$1" in
  new-session) name=$4; dir=$6; shift 7; echo "$name" >> "$live"; (cd "$dir" && bash -c "$2") ;;
  has-session) grep -qx "${3#=}" "$live" ;;
  kill-session) grep -vx "${3#=}" "$live" > "$live.new"; mv "$live.new" "$live" ;;
esac
'''


def sh(*args, cwd):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


class SSHRunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        for name, text in (('ssh', FAKE_SSH), ('tmux', FAKE_TMUX)):
            (self.bin / name).write_text(text)
            (self.bin / name).chmod(0o755)
        self.remote_home = self.tmp / 'other-mac'
        self.remote_home.mkdir()
        self.env = {k: os.environ.get(k) for k in ('RUNWAY_HOME', 'FAKE_REMOTE_HOME')}
        os.environ['RUNWAY_HOME'] = str(self.tmp / 'this-mac' / '.runway')
        os.environ['FAKE_REMOTE_HOME'] = str(self.remote_home)

        origin = self.tmp / 'origin.git'
        sh('init', '--quiet', '--bare', '-b', 'main', str(origin), cwd=self.tmp)
        seed = self.tmp / 'seed'
        sh('clone', '--quiet', str(origin), str(seed), cwd=self.tmp)
        (seed / 'runway.json').write_text(json.dumps({'check_cmd': 'test -f README.md'}))
        (seed / 'README.md').write_text('hello\n')
        sh('add', '-A', cwd=seed)
        sh('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '--quiet', '-m', 'seed', cwd=seed)
        sh('push', '--quiet', 'origin', 'main', cwd=seed)
        self.origin = origin
        self.local = self.tmp / 'local'
        sh('clone', '--quiet', str(origin), str(self.local), cwd=self.tmp)
        self.repo = {'name': 'demo', 'path': str(self.local), 'base': 'main'}
        self.runner = SSHRunner('second-mac', ssh=str(self.bin / 'ssh'), tmux=str(self.bin / 'tmux'))

    def tearDown(self):
        for k, v in self.env.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def remote(self, *parts):
        return self.remote_home.joinpath('.runway', *parts)

    def test_root_is_the_other_macs_home(self):
        self.assertEqual(self.runner.root(), f'{self.remote_home}/.runway')
        self.assertEqual((self.bin / 'hosts').read_text().split(), ['second-mac'])

    def test_worktree_clones_once_and_checks_out_the_branch_there(self):
        wt = self.runner.worktree(self.repo, 'T1', 1, 'origin/main', branch='rw/T1')
        self.assertEqual(wt, str(self.remote('worktrees', 'demo', 'T1-1')))
        self.assertTrue(self.remote('repos', 'demo', '.git').is_dir())
        self.assertEqual(sh('rev-parse', '--abbrev-ref', 'HEAD', cwd=wt), 'rw/T1')
        self.assertTrue(Path(wt, 'README.md').exists())
        self.assertFalse((Path(os.environ['RUNWAY_HOME']) / 'worktrees').exists())   # nothing on this Mac
        main = sh('rev-parse', 'origin/main', cwd=self.local)
        self.assertEqual(self.runner.rev(self.repo, 'origin/main'), main)
        self.assertTrue(self.runner.has_ref(self.repo, 'origin/main'))
        self.assertFalse(self.runner.has_ref(self.repo, 'origin/nope'))
        self.runner.worktree(self.repo, 'T1', 2, main)                                # the clone is reused
        self.assertEqual(self.runner.config(self.repo), {'check_cmd': 'test -f README.md'})

    def test_a_run_goes_over_and_its_folder_comes_back(self):
        wt = self.runner.worktree(self.repo, 'T1', 1, 'origin/main', branch='rw/T1')
        run_dir = db.home() / 'runs' / 'T1' / '1'
        run_dir.mkdir(parents=True)
        (run_dir / 'prompt.md').write_text(f'Write the outcome to {run_dir / "outcome.json"}.\n')
        # A worker line shaped like worker.command's: outcome, log and exit code in the run folder.
        line = (f"echo '{{\"status\": \"done\"}}' > {run_dir / 'outcome.json'}; "
                f"echo ran > {run_dir / 'log'} 2>&1; echo $? > {run_dir / 'exit'}")
        self.runner.start('rw-T1-1', wt, line)

        there = self.remote('runs', 'T1', '1')
        self.assertIn(str(there), (there / 'prompt.md').read_text())          # the prompt names the other Mac's path
        self.assertTrue((there / 'outcome.json').exists())
        self.assertFalse((run_dir / 'outcome.json').exists())                 # not back yet: still running

        self.assertTrue(self.runner.alive('rw-T1-1'))
        self.runner.stop('rw-T1-1')
        self.assertFalse(self.runner.alive('rw-T1-1'))
        fresh = SSHRunner('second-mac', ssh=str(self.bin / 'ssh'), tmux=str(self.bin / 'tmux'))  # a restarted loop
        fresh.collect(run_dir)
        self.assertEqual(json.loads((run_dir / 'outcome.json').read_text()), {'status': 'done'})
        self.assertEqual((run_dir / 'exit').read_text().strip(), '0')
        self.assertIn(str(run_dir), (run_dir / 'prompt.md').read_text())      # this Mac's prompt is left as it was

    def test_an_unreachable_mac_does_not_end_a_run(self):
        (self.bin / 'down').touch()
        self.runner._root = f'{self.remote_home}/.runway'
        self.assertTrue(self.runner.alive('rw-T1-1'))
        with self.assertRaises(db.RunwayError):
            self.runner.worktree(self.repo, 'T1', 1, 'origin/main', branch='rw/T1')

    def test_commit_check_and_push_happen_on_the_other_mac(self):
        wt = self.runner.worktree(self.repo, 'T1', 1, 'origin/main', branch='rw/T1')
        self.assertIsNone(self.runner.commit(wt, 'T1: nothing'))
        Path(wt, 'NEW.md').write_text('new\n')
        sha = self.runner.commit(wt, 'T1: add NEW')
        self.assertEqual(sha, self.runner.head(wt))
        self.assertEqual(self.runner.check(wt, 'test -f NEW.md'), (True, ''))
        ok, out = self.runner.check(wt, 'echo nope; exit 3')
        self.assertFalse(ok)
        self.assertEqual(out, 'nope')
        self.runner.push(wt, 'rw/T1')
        self.assertEqual(sh('rev-parse', 'refs/heads/rw/T1', cwd=self.origin), sha)
        self.runner.remove(self.repo, wt)
        self.assertFalse(Path(wt).exists())
        self.assertNotIn(wt, sh('worktree', 'list', cwd=self.remote('repos', 'demo')))

    def test_run_folder_reads_a_real_worker_line(self):
        run_dir = db.home() / 'runs' / 'T7' / '3'
        for agent in ('claude', 'codex'):
            line = worker.command(agent, run_dir / 'prompt.md', run_dir, Path('/x/wt'), ['make test'],
                                  session_id='abc')
            self.assertEqual(run_folder(line), run_dir)
        self.assertIsNone(run_folder('echo hi > /tmp/log'))


if __name__ == '__main__':
    unittest.main()
