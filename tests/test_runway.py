"""pm-runway's runway CLI: the readiness check, the journal, the loop's tick and the gate.

Run from the repo root: python3 -m unittest discover -s tests
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'pm-runway'))

from runway import gate as gt  # noqa: E402
from runway import journal as jn  # noqa: E402
from runway import loop as lp  # noqa: E402
from runway import tickets as tk  # noqa: E402

TICKET = """---
id: {id}
chunk: inbox
spec: docs/specs/2026-10-23-inbox.md
blocked_by: [{blocked}]
touches: [{touches}]
risk: {risk}
risk_reason: {reason}
model: any
status: ready-for-agent
---
# {title}

## What to build
The inbox shows a thing.

## Blocked by
{blocked_text}

## Acceptance
- [ ] A1: The thing shows. Verify: `python3 -m unittest`

## Context
Spec: docs/specs/2026-10-23-inbox.md, user story 1.
"""


def write_ticket(folder, n, tid, title, blocked='', touches='web', risk='low', reason='copy change only'):
    (folder / f'{n:02d}-{tid}.md').write_text(TICKET.format(
        id=tid, title=title, blocked=blocked, touches=touches, risk=risk, reason=reason,
        blocked_text=blocked or 'None (can start immediately)'))


class Fixture(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        os.environ['PM_RUNWAY_HOME'] = str(base / 'home')
        self.repo = base / 'app'
        self.dir = self.repo / 'docs/maps/inbox/tickets'
        self.dir.mkdir(parents=True)
        write_ticket(self.dir, 1, 'inbox-01', 'Unread flag', touches='api')
        write_ticket(self.dir, 2, 'inbox-02', 'Unread badge', blocked='inbox-01', touches='web')
        write_ticket(self.dir, 3, 'inbox-03', 'Mark all read', touches='settings')
        self.cfg = {'orca': 'orca', 'builder': 'claude', 'max_running': 3, 'machines': [
            {'name': 'm6', 'on': None, 'slots': 1},
            {'name': 'mini', 'on': 'mini', 'slots': 1, 'repos': {'app': 'repo:app'}}]}

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop('PM_RUNWAY_HOME', None)


class ReadinessTest(Fixture):
    def test_good_chunk_is_ready(self):
        self.assertEqual(tk.check_all(tk.load_dir(self.dir)), {})

    def test_each_rule_is_reported(self):
        bad = self.dir / '04-bad.md'
        bad.write_text('---\nid: inbox-04\nchunk: inbox\nrisk: low\nblocked_by: [nope]\n---\n# Bad\n\n'
                       '## Acceptance\n- [ ] A1: something\n')
        probs = tk.check_all(tk.load_dir(self.dir))['inbox-04']
        joined = '\n'.join(probs)
        for needle in ('missing header field: spec', 'risk_reason', 'What to build', 'Verify:',
                       'Context', "unknown ticket 'nope'", 'touches'):
            self.assertIn(needle, joined)

    def test_cycle_is_caught(self):
        write_ticket(self.dir, 4, 'inbox-04', 'A', blocked='inbox-05')
        write_ticket(self.dir, 5, 'inbox-05', 'B', blocked='inbox-04')
        report = tk.check_all(tk.load_dir(self.dir))
        self.assertTrue(any('blocking cycle' in p for ps in report.values() for p in ps))

    def test_start_refuses_a_failing_chunk(self):
        (self.dir / '04-bad.md').write_text('---\nid: inbox-04\n---\n# Bad\n')
        with self.assertRaises(jn.JournalError):
            jn.start(self.repo, 'docs/maps/inbox/tickets')

    def test_cli_check_exit_codes(self):
        cli = [sys.executable, str(ROOT / 'pm-runway/runway/runway.py'), 'check']
        ok = subprocess.run(cli + [str(self.dir)], capture_output=True, text=True)
        self.assertEqual(ok.returncode, 0, ok.stdout + ok.stderr)
        (self.dir / '04-bad.md').write_text('---\nid: inbox-04\n---\n# Bad\n')
        bad = subprocess.run(cli + [str(self.dir)], capture_output=True, text=True)
        self.assertEqual(bad.returncode, 1)
        self.assertIn('NOT READY', bad.stdout)


class FakeOrca:
    def __init__(self):
        self.started, self.inbox_msgs, self.acked, self.n = [], [], [], 0

    def run_create(self, objective):
        return 'run-1'

    def inbox(self, run):
        msgs, self.inbox_msgs = self.inbox_msgs, []
        return ('dl-%d' % len(self.acked) if msgs else None), msgs

    def ack(self, run, delivery):
        self.acked.append(delivery)

    def start(self, argv):
        self.n += 1
        self.started.append(argv)
        return f'd{self.n}'

    def release(self, dispatch):
        pass

    def done(self, dispatch, outcome='succeeded', subject='done', body=''):
        self.inbox_msgs.append({'id': f'm-{dispatch}', 'type': 'worker_done', 'subject': subject, 'body': body,
                                'payload': json.dumps({'taskId': 't', 'dispatchId': dispatch, 'outcome': outcome})})


class FakeGit:
    def __init__(self):
        self.remote, self.merged, self.conflict = {}, [], set()

    def remote_sha(self, branch):
        return self.remote.get(branch)

    def ensure_branch(self, branch, base):
        self.remote.setdefault(branch, 'c' * 40)

    def merge(self, data, ticket, branch, sha, check_cmd):
        if ticket in self.conflict:
            self.conflict.discard(ticket)
            return False, 'merge conflict with the chunk branch'
        self.merged.append(ticket)
        new = f'{len(self.merged):040d}'
        self.remote[data['branch']] = new
        return True, new

    def open_pr(self, data):
        return '7'


class FakeGH:
    def __init__(self, head):
        self.head, self.merges, self.files = head, [], [{'path': 'web/inbox.js'}]

    def pr(self, repo, number):
        return {'headRefOid': self.head(), 'headRefName': 'chunk/inbox', 'baseRefName': 'main',
                'state': 'OPEN', 'isDraft': True, 'files': self.files}

    def checks(self, repo, number):
        return [{'name': 'test', 'state': 'SUCCESS'}]

    def merge(self, repo, number, head, method):
        self.merges.append((number, head))


class LoopTest(Fixture):
    def setUp(self):
        super().setUp()
        self.path, self.data = jn.start(self.repo, 'docs/maps/inbox/tickets')
        self.orca, self.git = FakeOrca(), FakeGit()
        self.gh = FakeGH(lambda: self.git.remote['chunk/inbox'])

    def tick(self):
        return lp.tick(self.data, self.cfg, self.orca, self.git, gh=self.gh, log=lambda *_: None, repo_cfg={})

    def dispatch_of(self, ticket, kind='build-dispatched'):
        return [e['dispatch'] for e in self.data['events'] if e['kind'] == kind and e.get('ticket') == ticket][-1]

    def build_ok(self, ticket):
        self.git.remote[f'rw/{ticket}'] = (ticket[-1] * 40)
        self.orca.done(self.dispatch_of(ticket))

    def review(self, ticket, verdict='pass', risk='low'):
        sha = jn.states(self.data)[ticket]['sha']
        self.orca.done(self.dispatch_of(ticket, 'review-dispatched'),
                       subject=f'VERDICT: {verdict} RISK: {risk} SHA: {sha}', body='findings: none')

    def test_frontier_and_slots(self):
        self.tick()
        st = jn.states(self.data)
        # inbox-02 waits on inbox-01; two machines with one slot each take 01 and 03.
        self.assertEqual(st['inbox-01']['state'], 'building')
        self.assertEqual(st['inbox-03']['state'], 'building')
        self.assertEqual(st['inbox-02']['state'], 'queued')
        self.assertEqual({st['inbox-01']['machine'], st['inbox-03']['machine']}, {'m6', 'mini'})
        remote = next(a for a in self.orca.started if '--on' in a)
        self.assertIn('repo:app', remote)
        self.assertEqual(remote[remote.index('--base-branch') + 1], 'chunk/inbox')

    def test_pause_starts_nothing(self):
        lp.set_paused(True)
        self.tick()
        self.assertEqual(self.orca.started, [])
        lp.set_paused(False)
        self.tick()
        self.assertEqual(len(self.orca.started), 2)

    def test_review_is_the_other_model(self):
        self.tick()
        self.build_ok('inbox-01')
        self.tick()
        review = next(a for a in self.orca.started if a[a.index('--task-title') + 1].startswith('review'))
        self.assertEqual(review[review.index('--agent') + 1], 'codex')
        with self.assertRaises(jn.JournalError):
            jn.record(self.data, 'reviewed', ticket='inbox-01', verdict='pass', sha='1' * 40, agent='claude')

    def test_done_without_a_pushed_branch_is_a_failure(self):
        self.tick()
        self.orca.done(self.dispatch_of('inbox-01'))
        self.tick()
        self.assertEqual(jn.states(self.data)['inbox-01']['state'], 'building')  # the fix pass started
        self.assertEqual(jn.states(self.data)['inbox-01']['builds'], 2)

    def test_a_review_for_another_commit_fails(self):
        self.tick()
        self.build_ok('inbox-01')
        self.tick()
        self.orca.done(self.dispatch_of('inbox-01', 'review-dispatched'), subject='VERDICT: pass RISK: low SHA: deadbeef')
        self.tick()
        st = jn.states(self.data)['inbox-01']
        self.assertNotIn('inbox-01', self.git.merged)
        self.assertEqual(st['builds'], 2)

    def test_two_failed_builds_need_you(self):
        self.tick()
        self.orca.done(self.dispatch_of('inbox-03'), outcome='failed')
        self.tick()
        self.orca.done(self.dispatch_of('inbox-03'), outcome='failed')
        self.tick()
        self.assertEqual(jn.states(self.data)['inbox-03']['state'], 'needs-you')
        self.assertIn('Waiting on you', lp.screen(self.data))

    def run_to_end(self, risk='low'):
        self.tick()
        for t in ('inbox-01', 'inbox-03'):
            self.build_ok(t)
        self.tick()
        for t in ('inbox-01', 'inbox-03'):
            self.review(t, risk=risk)
        self.tick()  # both land; inbox-02 is now on the frontier
        self.assertEqual(sorted(self.git.merged), ['inbox-01', 'inbox-03'])
        self.build_ok('inbox-02')
        self.tick()
        self.review('inbox-02')
        self.tick()  # lands and starts the whole-chunk review
        chunk_review = self.orca.started[-1]
        self.assertIn('review chunk inbox', chunk_review)
        head = self.git.remote['chunk/inbox']
        self.orca.done([e['dispatch'] for e in self.data['events'] if e['kind'] == 'chunk-review-dispatched'][0],
                       subject=f'VERDICT: pass SHA: {head}')
        self.tick()

    def test_low_risk_chunk_merges_through_the_gate(self):
        self.run_to_end()
        self.assertEqual(self.gh.merges, [('7', self.git.remote['chunk/inbox'])])
        self.assertTrue(lp.done(self.data))

    def test_a_raised_risk_stops_at_the_gate(self):
        self.run_to_end(risk='not-low')
        self.assertEqual(self.gh.merges, [])
        self.assertIn('not low risk', lp.screen(self.data))

    def test_sensitive_path_needs_you(self):
        self.gh.files = [{'path': 'db/migrations/001.sql'}]
        self.run_to_end()
        self.assertEqual(self.gh.merges, [])

    def test_conflict_goes_back_for_a_fix(self):
        self.tick()
        self.build_ok('inbox-01')
        self.tick()
        self.review('inbox-01')
        self.git.conflict.add('inbox-01')
        self.tick()
        st = jn.states(self.data)['inbox-01']
        self.assertEqual(st['state'], 'building')
        fix = self.orca.started[-1]
        self.assertEqual(fix[fix.index('--base-branch') + 1], 'rw/inbox-01')
        self.assertIn('merge conflict', fix[fix.index('--spec') + 1])

    def test_board_has_the_columns(self):
        self.tick()
        self.build_ok('inbox-01')
        self.tick()
        lp.heartbeat(self.data, 'running')
        page = (Path(os.environ['PM_RUNWAY_HOME']) / 'board.html').read_text()
        for col in ('Queued (1)', 'Implementing (1)', 'In review (1)', 'Merged (0)', 'Waiting on you (0)'):
            self.assertIn(col, page)
        self.assertIn('last pickup inbox-03 on mini', page)

    def test_journal_survives_a_restart(self):
        self.tick()
        jn.save(self.path, self.data)
        _, again = jn.load(self.repo, 'inbox')
        self.assertEqual(jn.states(again), jn.states(self.data))


class GateTest(Fixture):
    def test_tickets_changed_after_start_count_as_sensitive(self):
        self.assertEqual(gt.sensitive_hits(['docs/maps/inbox/tickets/01-x.md'], gt.DEFAULT_SENSITIVE),
                         ['docs/maps/inbox/tickets/01-x.md'])


class FindTest(unittest.TestCase):
    def test_ids_are_found_in_any_receipt_shape(self):
        self.assertEqual(lp.find({'result': {'dispatch': {'id': 'x'}}}, 'dispatchId', ('dispatch', 'id')), 'x')
        self.assertEqual(lp.find({'result': {'dispatchId': 'y'}}, 'dispatchId'), 'y')
        with self.assertRaises(lp.LoopError):
            lp.find({'ok': True}, 'runId')


if __name__ == '__main__':
    unittest.main()
