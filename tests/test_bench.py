import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from runway import bench, db, stats, tickets
from runway.runner import LocalRunner

# Stub engines: write a file and a "done" outcome where the prompt says, and print usage like the real ones.
STUB = '''#!/usr/bin/env python3
import json, re, sys
prompt = " ".join(a for a in sys.argv[1:] if len(a) > 200)
out = re.search(r"Write exactly one JSON file to (\\S+)", prompt).group(1)
open("chars.py", "w").write("def count(t):\\n    return len(t)\\n")
json.dump({"status": "done", "summary": "stub"}, open(out, "w"))
if "{engine}" == "claude":
    print(json.dumps({"total_cost_usd": 0.42, "usage": {"input_tokens": 1000, "output_tokens": 50}}))
else:
    print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 3000, "output_tokens": 70}}))
'''


def sh(*args, cwd):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


class BenchTest(unittest.TestCase):
    """A4: bench re-runs a done ticket with each engine from its base commit, records results, pushes nothing."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.env = dict(os.environ)
        home, stubs = root / 'home', root / 'stubs'
        home.mkdir()
        stubs.mkdir()
        for engine in ('claude', 'codex'):
            (stubs / engine).write_text(STUB.replace('{engine}', engine))
            (stubs / engine).chmod(0o755)
        py = Path('/usr/bin/python3')
        (home / '.zprofile').write_text(f'export PATH="{stubs}:{py.parent}:/usr/bin:/bin"\n')
        os.environ.update(HOME=str(home), SHELL='/bin/zsh', RUNWAY_HOME=str(root / 'runway'))
        self.origin = root / 'origin.git'
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(self.origin)], check=True)
        clone = root / 'app'
        subprocess.run(['git', 'clone', '-q', str(self.origin), str(clone)], check=True, capture_output=True)
        (clone / 'README.md').write_text('app\n')
        sh('add', '-A', cwd=clone)
        sh('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'init', cwd=clone)
        self.base = sh('rev-parse', 'HEAD', cwd=clone)
        (clone / 'chars.py').write_text('def count(t): return len(t)\n')
        sh('add', '-A', cwd=clone)
        sh('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', 'T-1: Count characters', cwd=clone)
        built = sh('rev-parse', 'HEAD', cwd=clone)
        sh('push', '-q', 'origin', 'HEAD:refs/heads/main', cwd=clone)
        self.con = db.connect()
        self.con.execute("INSERT INTO repos(name, path, slug, base, check_cmd) VALUES ('app', ?, 'someone/app', 'main', "
                         "'test -f chars.py')", (str(clone),))
        self.tid = tickets.file_batch(self.con, 'app', [{
            'title': 'Count characters', 'risk': 'low', 'risk_reason': 'new module',
            'acceptance': ['A1: chars.py defines count. Verify: `grep -q "def count" chars.py`']}])[0]
        db.update_ticket(self.con, self.tid, state='done', merged_by='gate', merged_at=db.now())
        self.con.execute("INSERT INTO runs(ticket, kind, agent, runner, sha, started_at, ended_at, outcome) "
                         "VALUES (?, 'build', 'claude', 'This Mac', ?, 0, 1, 'done')", (self.tid, built))

    def tearDown(self):
        self.con.close()
        os.environ.clear()
        os.environ.update(self.env)
        self.tmp.cleanup()

    def refs(self):
        return sh('for-each-ref', '--format=%(refname) %(objectname)', cwd=self.origin)

    def test_two_engines_two_results_nothing_pushed(self):
        before = self.refs()
        results = bench.run(self.con, [self.tid], ('claude', 'codex'), runner=LocalRunner(), log=lambda *_: None)
        self.assertEqual(self.refs(), before)                                   # no branch pushed
        by = {r['agent']: r for r in results}
        self.assertEqual(set(by), {'claude', 'codex'})
        for r in results:
            self.assertEqual(r['result'], 'pass', r)
            self.assertIsInstance(r['minutes'], float)
        self.assertEqual(by['claude']['cost_usd'], 0.42)
        self.assertIsNone(by['codex']['cost_usd'])                              # tokens only, never an estimate
        self.assertEqual(by['codex']['tokens'], 3070)
        rows = self.con.execute('SELECT base_sha, worktree FROM bench').fetchall()
        self.assertEqual({r['base_sha'] for r in rows}, {self.base})          # from the original base commit
        self.assertTrue(all(not Path(r['worktree']).exists() for r in rows))   # worktrees cleaned up
        table = stats.snapshot(self.con)['bench']
        self.assertEqual([(r['ticket'], r['agent'], r['result']) for r in table],
                         [(self.tid, 'claude', 'pass'), (self.tid, 'codex', 'pass')])

    def test_needs_both_engines(self):
        self.con.execute("UPDATE agents SET signed_in=0 WHERE kind='codex'")
        with self.assertRaisesRegex(db.RunwayError, 'needs both Claude Code and Codex'):
            bench.run(self.con, [self.tid], log=lambda *_: None)

    def test_only_done_tickets(self):
        db.update_ticket(self.con, self.tid, state='queued')
        with self.assertRaisesRegex(db.RunwayError, 're-runs done tickets'):
            bench.run(self.con, [self.tid], log=lambda *_: None)

    def test_verify_commands(self):
        t = {'acceptance': '["A1: x. Verify: `python3 -m unittest -q`", "A2: y. Verify: make test", "A3: no verify"]'}
        self.assertEqual(bench.verify_commands(t), ['python3 -m unittest -q', 'make test'])


if __name__ == '__main__':
    unittest.main()
