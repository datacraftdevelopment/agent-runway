import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from runway import db, stats, take, tickets
from runway.loop import Loop
from runway.runner import LocalRunner


def sh(*args, cwd):
    return subprocess.run(['git', '-C', str(cwd), *args], check=True, capture_output=True, text=True).stdout.strip()


class NoTmuxRunner(LocalRunner):
    """Real git worktrees and pushes; workers are never started."""

    def __init__(self):
        super().__init__()
        self.started, self.stopped = [], []

    def start(self, name, workdir, line):
        self.started.append((name, workdir))

    def capacity(self):
        return None                         # never this Mac's real load: tests don't depend on it

    def alive(self, name):
        return name in [n for n, _ in self.started] and name not in self.stopped

    def stop(self, name):
        self.stopped.append(name)


class FakeGitHub:
    def __init__(self, state='OPEN'):
        self.state, self.merged, self.closed = state, [], []

    def pr(self, path, number):
        return {'state': self.state, 'headRefOid': 'x', 'files': []}

    def merge(self, path, number, head, method='merge'):
        self.merged.append((number, head))
        self.state = 'MERGED'

    def close(self, path, number, comment=None):
        self.closed.append((number, comment))
        self.state = 'CLOSED'

    def checks(self, path, number):
        return []

    def create_pr(self, *a):
        return 7


class TakeBackTest(unittest.TestCase):
    """A2: take a needs-you ticket back, commit on its branch, give it back; the build starts from that commit."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        os.environ['RUNWAY_HOME'] = str(root / 'home')
        self.origin = root / 'origin.git'
        subprocess.run(['git', 'init', '-q', '--bare', '-b', 'main', str(self.origin)], check=True)
        self.clone = root / 'app'
        subprocess.run(['git', 'clone', '-q', str(self.origin), str(self.clone)], check=True, capture_output=True)
        self.commit(self.clone, 'README.md', 'app\n', 'init', branch='main')
        self.con = db.connect()
        self.con.execute("INSERT INTO repos(name, path, slug, base) VALUES ('app', ?, 'someone/app', 'main')",
                         (str(self.clone),))
        self.tid = tickets.file_batch(self.con, 'app', [{'title': 'Count words', 'risk': 'not-low',
                                                         'acceptance': ['A1: it counts']}])[0]
        self.runner = NoTmuxRunner()
        # A finished build: a commit pushed on rw/T-1, its worktree kept, then the gate asked the person.
        wt = self.runner.worktree(db.repo(self.con, 'app'), self.tid, 1, 'origin/main', branch=f'rw/{self.tid}')
        built = self.commit(wt, 'words.py', 'def count(t): return len(t.split())\n', 'T-1: Count words',
                            branch=f'rw/{self.tid}')
        run_dir = db.home() / 'runs' / self.tid / '1'
        run_dir.mkdir(parents=True)
        (run_dir / 'outcome.json').write_text('{"status": "done"}')
        self.con.execute("INSERT INTO runs(ticket, kind, agent, runner, dir, branch, stage, run_dir, session_id, sha, "
                         "started_at, ended_at, outcome) VALUES (?, 'build', 'codex', 'This Mac', ?, ?, 'reviews', ?, "
                         "'thread-1', ?, 0, 1, 'done')", (self.tid, str(wt), f'rw/{self.tid}', str(run_dir), built))
        db.update_ticket(self.con, self.tid, state='needs_you', branch=f'rw/{self.tid}', sha=built, pr=7,
                         review='Claude Code: pass', function_review='Codex: fail',
                         question={'kind': 'merge', 'reason': 'not_low_risk', 'text': 'Merge PR #7?'})
        self.built = built

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def commit(self, wt, name, text, message, branch):
        (Path(wt) / name).write_text(text)
        sh('add', '-A', cwd=wt)
        sh('-c', 'user.name=t', '-c', 'user.email=t@t', 'commit', '-q', '-m', message, cwd=wt)
        sh('push', '-q', 'origin', f'HEAD:refs/heads/{branch}', cwd=wt)
        return sh('rev-parse', 'HEAD', cwd=wt)

    def test_take_prompt_and_give(self):
        tid = self.tid
        prompt_only = take.prompt(self.con, tid)
        self.assertEqual(db.ticket(self.con, tid)['state'], 'needs_you')        # --prompt changes nothing
        self.assertEqual(prompt_only.splitlines()[0], f'Use the runway take-back skill on ticket {tid} in app.')
        self.assertIn(f'on branch rw/{tid}', prompt_only)
        self.assertIn(f'runway done {tid} --note', prompt_only)
        self.assertIn(f'runway drop {tid} --reason', prompt_only)
        self.assertIn('Never leave it taken back.', prompt_only)
        self.assertIn('code review: Claude Code: pass; function review: Codex: fail', prompt_only)
        self.assertIn('Last run: Codex, session thread-1, stopped at reviews.', prompt_only)
        self.assertIn(f'runs/{tid}/1/ (transcript.jsonl, outcome.json, reviews/)', prompt_only)
        self.assertIn(f'runway show {tid}', prompt_only)
        self.assertIn(f'runway give {tid} (Runway reviews it again)', prompt_only)

        wt, branch = take.take(self.con, tid, runner=self.runner)
        self.assertEqual(branch, f'rw/{tid}')
        self.assertEqual(sh('rev-parse', '--abbrev-ref', 'HEAD', cwd=wt), branch)
        self.assertEqual(sh('rev-parse', 'HEAD', cwd=wt), self.built)
        t = db.ticket(self.con, tid)
        self.assertEqual((t['state'], t['taken']), ('taken', 1))
        self.assertEqual(json.loads(t['question'])['go_label'], 'Give back')
        self.assertEqual(take.take(self.con, tid, runner=self.runner), (wt, branch))   # twice is harmless
        self.assertEqual(db.ticket(self.con, tid)['taken'], 1)
        self.assertEqual(stats.waiting(self.con)[0]['reason'], 'taken_back')

        (Path(wt) / 'words.py').write_text('def count(t):\n    return len(t.split())\n')
        with self.assertRaisesRegex(db.RunwayError, 'uncommitted'):
            take.give(self.con, tid, runner=self.runner)
        mine = self.commit(wt, 'words.py', 'def count(t):\n    return len(t.split())\n', 'fix by the person',
                           branch='scratch')
        head = take.give(self.con, tid, runner=self.runner)
        self.assertEqual(head, mine)
        self.assertEqual(sh('rev-parse', f'refs/heads/{branch}', cwd=self.origin), mine)
        t = db.ticket(self.con, tid)
        self.assertEqual((t['state'], t['take_dir']), ('queued', None))

        # The next build starts from the person's commit, and changing nothing is fine: its reviews run on it.
        loop = Loop(self.con, runner=self.runner, github=FakeGitHub(), log=lambda *_: None)
        loop.tick()
        build = self.con.execute("SELECT * FROM runs WHERE ticket=? AND ended_at IS NULL", (tid,)).fetchone()
        self.assertEqual(sh('rev-parse', 'HEAD', cwd=build['dir']), mine)
        self.assertEqual(build['run_dir'], str(db.home() / 'runs' / tid / '2'))
        prompt = (Path(build['run_dir']) / 'prompt.md').read_text()
        self.assertIn('took this ticket over', prompt)
        (Path(build['run_dir']) / 'outcome.json').write_text('{"status": "done", "summary": "nothing missing"}')
        self.runner.stopped.append(build['tmux'])                       # the worker ends
        loop.tick()
        t = db.ticket(self.con, tid)
        self.assertEqual((t['state'], t['sha']), ('reviewing', mine))
        self.assertEqual({r['role'] for r in self.con.execute(
            "SELECT role FROM runs WHERE ticket=? AND kind='review' AND ended_at IS NULL", (tid,))}, {'code', 'function'})

    def test_take_stops_a_running_worker(self):
        db.update_ticket(self.con, self.tid, state='building')
        self.con.execute("INSERT INTO runs(ticket, kind, agent, runner, tmux, started_at) VALUES (?, 'build', 'claude', "
                         "'This Mac', 'rw-live', 2)", (self.tid,))
        take.take(self.con, self.tid, runner=self.runner)
        self.assertIn('rw-live', self.runner.stopped)
        self.assertEqual(self.con.execute("SELECT outcome FROM runs WHERE tmux='rw-live'").fetchone()[0], 'taken')

    def test_show_lists_every_run_and_its_record(self):
        out = take.show(self.con, self.tid)
        self.assertIn('A1: it counts', out)
        self.assertIn('1. build by codex: done, stopped at reviews', out)
        self.assertIn('outcome.json', out)
        self.assertIn('session: thread-1', out)

    def test_done_pushes_merges_and_records_the_go_once(self):
        tid = self.tid
        wt, branch = take.take(self.con, tid, runner=self.runner)
        mine = self.commit(wt, 'words.py', 'def count(t):\n    return len(t.split())\n', 'finished', branch=branch)
        gh = FakeGitHub()
        self.assertIn('merged PR #7', take.done(self.con, tid, 'looks right', github=gh, runner=self.runner))
        self.assertEqual(gh.merged, [(7, mine)])                       # merged at the person's own head
        t = db.ticket(self.con, tid)
        self.assertEqual((t['state'], t['merged_by'], t['take_dir']), ('done', 'you', None))
        self.assertFalse(Path(wt).exists())
        self.assertEqual(self.con.execute("SELECT answer, note FROM answers").fetchall()[0][:], ('go', 'looks right'))
        self.assertIn('already done', take.done(self.con, tid, github=gh, runner=self.runner))
        self.assertEqual(len(gh.merged), 1)
        self.assertNotIn(tid, stats.window(self.con, 7)['hands_off_tickets'])

    def test_done_refuses_uncommitted_work(self):
        wt, _ = take.take(self.con, self.tid, runner=self.runner)
        (Path(wt) / 'words.py').write_text('half done\n')
        with self.assertRaisesRegex(db.RunwayError, 'uncommitted'):
            take.done(self.con, self.tid, github=FakeGitHub(), runner=self.runner)

    def test_drop_closes_the_pr_and_removes_worktrees_once(self):
        tid = self.tid
        wt, _ = take.take(self.con, tid, runner=self.runner)
        gh = FakeGitHub()
        self.assertIn('PR #7 closed', take.drop(self.con, tid, 'not needed', github=gh, runner=self.runner))
        self.assertEqual(gh.closed, [(7, 'Dropped in Runway: not needed')])
        self.assertFalse(Path(wt).exists())
        t = db.ticket(self.con, tid)
        self.assertEqual((t['state'], t['take_dir']), ('dropped', None))
        self.assertIn('already dropped', take.drop(self.con, tid, github=gh, runner=self.runner))
        self.assertEqual(len(gh.closed), 1)

    def test_board_knows_how_long_it_has_been_taken(self):
        from runway import status
        take.take(self.con, self.tid, runner=self.runner)
        self.con.execute("UPDATE stops SET at=? WHERE reason='taken_back'", (db.now() - 30 * 3600,))
        t = next(x for x in status.snapshot(self.con)['tickets'] if x['id'] == self.tid)
        self.assertTrue(t['taken'])
        self.assertGreaterEqual(t['taken_hours'], 30)

    def test_a_done_ticket_cannot_be_taken(self):
        db.update_ticket(self.con, self.tid, state='done')
        with self.assertRaisesRegex(db.RunwayError, 'only an open ticket'):
            take.take(self.con, self.tid, runner=self.runner)


if __name__ == '__main__':
    unittest.main()
