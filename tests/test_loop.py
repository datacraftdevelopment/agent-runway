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

    def head(self, workdir):
        return 'a1b2c3d4e5f6a7b8c9d0'

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
    engines = ('claude', 'codex')

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['RUNWAY_HOME'] = self.tmp.name
        self.con = db.connect()
        for kind in ('claude', 'codex'):
            self.con.execute('UPDATE agents SET signed_in=? WHERE kind=?', (int(kind in self.engines), kind))
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

    def live_runs(self, tid):
        return self.con.execute('SELECT * FROM runs WHERE ticket=? AND ended_at IS NULL ORDER BY id', (tid,)).fetchall()

    def live_run(self, tid, role=None):
        for r in self.live_runs(tid):
            if role is None or r['role'] == role:
                return r
        return None

    def finish(self, tid, filename, payload, log='', role=None):
        run = self.live_run(tid, role)
        d = db.run_dir(self.con, run)
        if payload is not None:
            (d / filename).write_text(json.dumps(payload))
        (d / 'log').write_text(log)
        self.runner.live.discard(run['tmux'])
        return run

    def build_done(self, tid):
        return self.finish(tid, 'outcome.json', {'status': 'done', 'summary': 'built it'})

    def review(self, tid, role, verdict='pass', risk='low', sha='a1b2c3d'):
        payload = {'verdict': verdict, 'risk': risk, 'sha': sha, 'findings': []}
        if role == 'function':
            payload.update(check='pass', lines=[{'line': 'A1: it counts', 'pass': verdict == 'pass',
                                                 'evidence': 'ran it'}])
        return self.finish(tid, 'review.json', payload, role=role)

    def both_reviews(self, tid, **kw):
        self.review(tid, 'code', **kw)
        self.review(tid, 'function', **kw)

    def state(self, tid):
        return db.ticket(self.con, tid)['state']

    def to_review(self, tid):
        self.loop.tick()
        self.build_done(tid)
        self.loop.tick()  # settles the build (commit, check, push, PR), then starts both reviews


class TwoEngines(LoopTest):
    def test_low_risk_ticket_runs_to_merged_after_both_reviews(self):
        tid = self.file()
        self.loop.tick()
        build = self.live_run(tid)
        self.assertEqual((self.state(tid), build['kind'], build['agent']), ('building', 'build', 'claude'))
        self.assertIn('--permission-mode dontAsk', self.runner.started[0][1])
        self.build_done(tid)
        self.loop.tick()
        t = db.ticket(self.con, tid)
        self.assertEqual((t['state'], t['pr'], t['branch']), ('reviewing', 1, f'rw/{tid}'))
        reviews = {r['role']: r for r in self.live_runs(tid)}
        self.assertEqual(set(reviews), {'code', 'function'})
        self.assertEqual(reviews['code']['agent'], 'codex')       # the code review prefers the other engine
        self.assertEqual(reviews['code']['sha'], 'a1b2c3d4e5f6a7b8c9d0')
        self.review(tid, 'code')
        self.loop.tick()
        self.assertEqual(self.state(tid), 'reviewing')           # one pass isn't enough
        self.assertEqual(self.gh.merged, [])
        self.review(tid, 'function')
        self.loop.tick()
        t = db.ticket(self.con, tid)
        self.assertEqual((t['state'], t['review']), ('done', 'Codex: pass'))
        self.assertTrue(t['function_review'].endswith(': pass'))
        self.assertEqual(self.gh.merged, [1])
        prompts = [(db.run_dir(self.con, r) / 'prompt.md').read_text()
                   for r in self.con.execute("SELECT * FROM runs WHERE kind='review' ORDER BY role")]
        self.assertIn('code reviewer, in a fresh session', prompts[0])
        self.assertIn('Walk each Acceptance line', prompts[1])

    def test_not_low_risk_waits_for_the_person(self):
        tid = self.file(risk='not_low', risk_reason=None)
        self.to_review(tid)
        self.both_reviews(tid)
        self.loop.tick()
        t = db.ticket(self.con, tid)
        q = json.loads(t['question'])
        self.assertEqual((t['state'], q['kind'], q['go_label'], q['reason']), ('needs_you', 'merge', 'Merge',
                                                                               'not_low_risk'))
        self.assertEqual(self.gh.merged, [])

    def test_a_review_can_raise_risk_never_lower(self):
        tid = self.file()
        self.to_review(tid)
        self.review(tid, 'code', risk='not_low')
        self.review(tid, 'function')
        self.loop.tick()
        t = db.ticket(self.con, tid)
        self.assertEqual((t['risk'], t['state'], t['review']), ('not_low', 'needs_you', 'Codex: pass, risk raised'))

    def test_pending_checks_wait(self):
        self.gh.checks_state = [{'name': 'test', 'state': 'IN_PROGRESS'}]
        tid = self.file()
        self.to_review(tid)
        self.both_reviews(tid)
        self.loop.tick()
        self.assertEqual(self.state(tid), 'merging')
        self.gh.checks_state = [{'name': 'test', 'state': 'SUCCESS'}]
        self.loop.tick()
        self.assertEqual(self.state(tid), 'done')

    def test_a_failing_function_review_stops_the_code_review_and_spends_the_fix_pass(self):
        tid = self.file()
        self.to_review(tid)
        code = self.live_run(tid, 'code')
        self.review(tid, 'function', verdict='fail')
        self.loop.tick()
        self.assertEqual(self.con.execute('SELECT outcome FROM runs WHERE id=?', (code['id'],)).fetchone()[0],
                         'cancelled')
        t = db.ticket(self.con, tid)
        self.assertEqual((t['state'], t['fix_passes']), ('building', 1))
        self.assertIn('failed the function review', t['note'])
        self.assertIn('A1: it counts: ran it', t['note'])
        self.build_done(tid)
        self.loop.tick()
        self.review(tid, 'code', verdict='fail')
        self.loop.tick()
        t = db.ticket(self.con, tid)
        q = json.loads(t['question'])
        self.assertEqual((t['state'], q['kind'], q['reason']), ('needs_you', 'failed', 'code_review_failed_twice'))

    def test_review_of_another_commit_fails(self):
        tid = self.file()
        self.to_review(tid)
        self.review(tid, 'code', sha='deadbee')
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
        self.assertEqual((t['state'], q['kind'], q['short'], q['go_label'], q['reason']),
                         ('needs_you', 'question', 'Which date format?', 'Use recommended', 'worker_question'))

    def test_usage_limit_with_two_engines_moves_any_tickets_to_the_other(self):
        tid = self.file()
        self.loop.tick()
        self.finish(tid, 'outcome.json', None, log='Claude AI usage limit reached|1999999999')
        other = self.file(title='Second')
        self.loop.tick()
        self.assertEqual(db.ticket(self.con, tid)['fix_passes'], 0)
        rest = self.con.execute("SELECT resting_until FROM agents WHERE kind='claude'").fetchone()['resting_until']
        self.assertGreater(rest, db.now())
        self.assertEqual({self.live_run(tid)['agent'], self.live_run(other)['agent']}, {'codex'})

    def test_nothing_changed_is_a_failure(self):
        self.runner.changes = False
        tid = self.file()
        self.loop.tick()
        self.build_done(tid)
        self.loop.tick()
        t = db.ticket(self.con, tid)
        self.assertEqual(t['fix_passes'], 1)
        self.assertIn('changed nothing', t['note'])

    def test_failed_check_records_its_reason(self):
        self.runner.check_ok = False
        tid = self.file()
        for _ in range(2):
            self.loop.tick()
            self.build_done(tid)
            self.loop.tick()
        q = json.loads(db.ticket(self.con, tid)['question'])
        self.assertEqual(q['reason'], 'check_failed_twice')

    def test_blockers_slots_and_pause(self):
        a = self.file(title='A')
        b = tickets.file_batch(self.con, 'demo', [{'title': 'B', 'acceptance': ['x'], 'blocked_by': [a]}])[0]
        c, d = self.file(title='C'), self.file(title='D')
        self.loop.tick()
        live = {r['ticket'] for r in self.con.execute('SELECT ticket FROM runs WHERE ended_at IS NULL')}
        self.assertEqual(live, {a, c})
        self.assertEqual(self.state(b), 'queued')
        self.assertEqual(self.state(d), 'queued')
        from runway import actions
        actions.pause(self.con, None, '1h')
        self.build_done(a)
        self.loop.tick()
        self.assertEqual(self.state(a), 'reviewing')
        self.assertIsNone(self.live_run(a))
        self.assertEqual(self.state(d), 'queued')


class OneEngine:
    """Runway works fully on one engine (Joe, 2026-10-25): both reviews run on it, in fresh sessions, and count."""

    def test_low_risk_ticket_auto_merges_after_two_same_engine_reviews(self):
        (engine,) = self.engines
        name = {'claude': 'Claude Code', 'codex': 'Codex'}[engine]
        tid = self.file()
        self.loop.tick()
        self.assertEqual(self.live_run(tid)['agent'], engine)
        self.build_done(tid)
        self.loop.tick()
        reviews = {r['role']: r['agent'] for r in self.live_runs(tid)}
        self.assertEqual(reviews, {'code': engine, 'function': engine})
        ids = [r['id'] for r in self.live_runs(tid)]
        build = self.con.execute("SELECT id, session_id FROM runs WHERE kind='build'").fetchone()
        self.assertNotIn(build['id'], ids)                          # each review is its own fresh run
        self.both_reviews(tid)
        self.loop.tick()
        t = db.ticket(self.con, tid)
        self.assertEqual(t['state'], 'done')
        self.assertEqual(t['review'], f'{name} (fresh session): pass')
        self.assertEqual(self.gh.merged, [1])

    def test_status_shows_only_this_engine(self):
        from runway import status
        self.assertEqual([a['kind'] for a in status.snapshot(self.con)['agents']], list(self.engines))

    def test_filing_for_the_missing_engine_is_refused(self):
        missing = 'codex' if self.engines == ('claude',) else 'claude'
        with self.assertRaisesRegex(db.RunwayError, 'not set up on this Mac'):
            self.file(agent=missing)
        self.file(agent=self.engines[0])
        self.file(agent='any')

    def test_a_usage_limit_parks_the_ticket_until_the_reset(self):
        from runway import status
        tid = self.file()
        self.loop.tick()
        self.finish(tid, 'outcome.json', None, log='usage limit reached|1999999999')
        self.loop.tick()
        t = db.ticket(self.con, tid)
        self.assertEqual((t['state'], t['fix_passes']), ('queued', 0))   # parked, not failed
        self.assertIsNone(self.live_run(tid))                          # no failover: nothing else to run on
        snap = status.snapshot(self.con)
        self.assertIsNotNone(snap['agents'][0]['resting_until'])
        self.assertIn('usage limit to reset at', snap['tickets'][0]['summary'])
        self.con.execute('UPDATE agents SET resting_until=NULL')
        self.loop.tick()
        self.assertEqual(self.live_run(tid)['agent'], self.engines[0])


class ClaudeOnly(OneEngine, LoopTest):
    engines = ('claude',)


class CodexOnly(OneEngine, LoopTest):
    engines = ('codex',)


class NoEngine(LoopTest):
    engines = ()

    def test_nothing_can_be_filed(self):
        with self.assertRaisesRegex(db.RunwayError, 'no engine is signed in'):
            self.file()


if __name__ == '__main__':
    unittest.main()
