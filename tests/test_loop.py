import json
import os
import tempfile
import unittest
from pathlib import Path

from runway import db, status, tickets
from runway.loop import Loop


class FakeRunner:
    """Runs nothing: a test decides when a run ends and what it wrote."""

    def __init__(self, home):
        self.home = Path(home)
        self.live = set()
        self.started = []
        self.check_ok = True
        self.changes = True
        self.cfg = {'check_cmd': 'python3 -m unittest -q'}
        self.pushed = []
        self.removed = []

    def run_dir(self, run_id):
        d = self.home / 'runs' / str(run_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def worktree(self, repo, ticket, run_id, ref, branch=None):
        wt = self.home / 'wt' / f'{ticket}-{run_id}'
        wt.mkdir(parents=True, exist_ok=True)
        return wt

    def has_ref(self, repo, ref):
        return True

    def start(self, name, workdir, line):
        self.live.add(name)
        self.started.append((name, line))

    def alive(self, name):
        return name in self.live

    def stop(self, name):
        self.live.discard(name)

    def check(self, workdir, cmd):
        return self.check_ok, 'ran the tests'

    def commit(self, workdir, message):
        return 'a1b2c3d4e5f6a7b8c9d0' if self.changes else None

    def push(self, workdir, branch):
        self.pushed.append(branch)

    def remove(self, repo, workdir):
        self.removed.append(workdir)

    def config(self, repo):
        return self.cfg


class FakeGitHub:
    def __init__(self):
        self.prs = {}
        self.checks_state = [{'name': 'test', 'state': 'SUCCESS'}]
        self.merged = []

    def create_pr(self, path, base, branch, title, body):
        n = len(self.prs) + 1
        self.prs[n] = {'number': n, 'state': 'OPEN', 'headRefOid': 'a1b2c3d4e5f6a7b8c9d0', 'files': [{'path': 'tally/x.py'}]}
        return n

    def pr(self, path, number):
        return self.prs[number]

    def checks(self, path, number):
        return self.checks_state

    def merge(self, path, number, head, method='merge'):
        self.merged.append(number)
        self.prs[number]['state'] = 'MERGED'


class LoopTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['RUNWAY_HOME'] = self.tmp.name
        self.con = db.connect()
        self.con.execute("INSERT INTO repos(name, path, base) VALUES ('demo', '/tmp/demo', 'main')")
        self.runner, self.gh = FakeRunner(self.tmp.name), FakeGitHub()
        self.loop = Loop(self.con, runner=self.runner, github=self.gh, log=lambda *_: None)

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def file(self, **kw):
        t = {'title': 'Count lines', 'risk': 'low', 'risk_reason': 'new module', 'acceptance': ['A1: it counts']}
        t.update(kw)
        return tickets.file_batch(self.con, 'demo', [t])[0]

    def live_run(self, tid):
        return self.con.execute('SELECT * FROM runs WHERE ticket=? AND ended_at IS NULL', (tid,)).fetchone()

    def finish(self, tid, filename, payload, log=''):
        run = self.live_run(tid)
        d = self.runner.run_dir(run['id'])
        if payload is not None:
            (d / filename).write_text(json.dumps(payload))
        (d / 'log').write_text(log)
        self.runner.live.discard(run['tmux'])
        return run

    def build_done(self, tid):
        return self.finish(tid, 'outcome.json', {'status': 'done', 'summary': 'built it'})

    def review(self, tid, verdict='pass', risk='low', sha='a1b2c3d'):
        return self.finish(tid, 'review.json', {'verdict': verdict, 'risk': risk, 'sha': sha, 'findings': []})

    def state(self, tid):
        return db.ticket(self.con, tid)['state']

    def test_low_risk_ticket_runs_to_merged(self):
        tid = self.file()
        self.loop.tick()
        build = self.live_run(tid)
        self.assertEqual((self.state(tid), build['kind'], build['agent']), ('building', 'build', 'claude'))
        self.assertIn('claude -p', self.runner.started[0][1])
        self.assertIn('--permission-mode dontAsk', self.runner.started[0][1])
        self.build_done(tid)
        self.loop.tick()  # settles the build (commit, check, push, PR), then starts the review
        t = db.ticket(self.con, tid)
        self.assertEqual((t['state'], t['pr'], t['branch']), ('reviewing', 1, f'rw/{tid}'))
        self.assertEqual(self.runner.pushed, [f'rw/{tid}'])
        review = self.live_run(tid)
        self.assertEqual((review['kind'], review['agent'], review['sha']), ('review', 'codex', 'a1b2c3d4e5f6a7b8c9d0'))
        self.assertIn('codex exec -s workspace-write', self.runner.started[1][1])
        self.review(tid)
        self.loop.tick()
        t = db.ticket(self.con, tid)
        self.assertEqual((t['state'], t['review']), ('done', 'Codex: pass'))
        self.assertEqual(self.gh.merged, [1])
        kinds = [e['kind'] for e in self.con.execute('SELECT kind FROM events ORDER BY id')]
        self.assertEqual(kinds, ['filed', 'start', 'start', 'review', 'review', 'merged'])
        self.assertEqual(status.snapshot(self.con)['tickets'][0]['pr'], '#1 merged')

    def test_not_low_risk_waits_for_the_person(self):
        tid = self.file(risk='not_low', risk_reason=None)
        self.loop.tick()
        self.build_done(tid)
        self.loop.tick()
        self.review(tid)
        self.loop.tick()
        t = db.ticket(self.con, tid)
        self.assertEqual(t['state'], 'needs_you')
        q = json.loads(t['question'])
        self.assertEqual((q['kind'], q['go_label']), ('merge', 'Merge'))
        self.assertIn('not low risk', q['text'])
        self.assertEqual(self.gh.merged, [])

    def test_review_can_raise_risk_never_lower(self):
        tid = self.file()
        self.loop.tick()
        self.build_done(tid)
        self.loop.tick()
        self.review(tid, risk='not_low')
        self.loop.tick()
        t = db.ticket(self.con, tid)
        self.assertEqual((t['risk'], t['state'], t['review']), ('not_low', 'needs_you', 'Codex: pass, risk raised'))

    def test_pending_checks_wait(self):
        self.gh.checks_state = [{'name': 'test', 'state': 'IN_PROGRESS'}]
        tid = self.file()
        self.loop.tick()
        self.build_done(tid)
        self.loop.tick()
        self.review(tid)
        self.loop.tick()
        self.assertEqual(self.state(tid), 'merging')
        self.gh.checks_state = [{'name': 'test', 'state': 'SUCCESS'}]
        self.loop.tick()
        self.assertEqual(self.state(tid), 'done')

    def test_failed_review_gets_one_fix_pass_then_asks(self):
        tid = self.file()
        self.loop.tick()
        self.build_done(tid)
        self.loop.tick()
        self.review(tid, verdict='fail')
        self.loop.tick()  # back to queued with the findings, and started again at once
        t = db.ticket(self.con, tid)
        self.assertEqual((t['state'], t['fix_passes']), ('building', 1))
        self.assertIn('failed the review', t['note'])
        self.build_done(tid)
        self.loop.tick()
        self.review(tid, verdict='fail')
        self.loop.tick()
        t = db.ticket(self.con, tid)
        self.assertEqual(t['state'], 'needs_you')
        self.assertEqual(json.loads(t['question'])['kind'], 'failed')

    def test_review_of_another_commit_fails(self):
        tid = self.file()
        self.loop.tick()
        self.build_done(tid)
        self.loop.tick()
        self.review(tid, sha='deadbee')
        self.loop.tick()
        self.assertEqual(db.ticket(self.con, tid)['fix_passes'], 1)

    def test_worker_question_goes_to_the_person(self):
        tid = self.file()
        self.loop.tick()
        self.finish(tid, 'outcome.json', {'status': 'needs_you', 'question': 'Which date format?',
                                          'recommended': 'Mon 26 Oct'})
        self.loop.tick()
        t = db.ticket(self.con, tid)
        q = json.loads(t['question'])
        self.assertEqual((t['state'], q['kind'], q['short'], q['go_label']),
                         ('needs_you', 'question', 'Which date format?', 'Use recommended'))

    def test_usage_limit_rests_the_agent_and_requeues_without_a_fix_pass(self):
        tid = self.file()
        self.loop.tick()
        self.finish(tid, 'outcome.json', None, log='Claude AI usage limit reached|1999999999')
        other = self.file(title='Second')
        self.loop.tick()
        t = db.ticket(self.con, tid)
        self.assertEqual(t['fix_passes'], 0)
        rest = self.con.execute("SELECT resting_until FROM agents WHERE kind='claude'").fetchone()['resting_until']
        self.assertGreater(rest, db.now())
        # Both tickets are Any, so with Claude resting they go to Codex.
        self.assertEqual({self.live_run(tid)['agent'], self.live_run(other)['agent']}, {'codex'})
        self.assertTrue(any(e['kind'] == 'limit' for e in self.con.execute('SELECT kind FROM events')))

    def test_nothing_changed_is_a_failure(self):
        self.runner.changes = False
        tid = self.file()
        self.loop.tick()
        self.build_done(tid)
        self.loop.tick()
        t = db.ticket(self.con, tid)
        self.assertEqual(t['fix_passes'], 1)
        self.assertIn('changed nothing', t['note'])

    def test_blockers_slots_and_pause(self):
        a = self.file(title='A')
        b = tickets.file_batch(self.con, 'demo', [{'title': 'B', 'acceptance': ['x'], 'blocked_by': [a]}])[0]
        c, d = self.file(title='C'), self.file(title='D')
        self.loop.tick()
        live = {r['ticket'] for r in self.con.execute('SELECT ticket FROM runs WHERE ended_at IS NULL')}
        self.assertEqual(live, {a, c})          # two slots on This Mac; B waits on A
        self.assertEqual(self.state(b), 'queued')
        self.assertEqual(self.state(d), 'queued')
        from runway import actions
        actions.pause(self.con, None, '1h')
        self.build_done(a)
        self.loop.tick()                         # finishing still happens while paused...
        self.assertEqual(self.state(a), 'reviewing')
        self.assertIsNone(self.live_run(a))      # ...but nothing new starts
        self.assertEqual(self.state(d), 'queued')

    def test_only_one_agent_signed_in_means_the_person_reviews(self):
        self.con.execute("UPDATE agents SET signed_in=0 WHERE kind='codex'")
        tid = self.file()
        self.loop.tick()
        self.build_done(tid)
        self.loop.tick()
        t = db.ticket(self.con, tid)
        self.assertEqual(t['state'], 'needs_you')
        self.assertIn('not signed in', json.loads(t['question'])['text'])


if __name__ == '__main__':
    unittest.main()
