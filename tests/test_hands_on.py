"""Hands-on tickets (Joe, 2026-10-26): filed beside the Runway batch, never started by the loop, done by the person
in their own session, and kept on the board and in the history as done by hand."""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from runway import db, stats, status, take, tickets
from runway.loop import Loop

from tests.test_loop import FakeRunner
from tests.test_take import FakeGitHub, NoTmuxRunner, sh


class FilingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['RUNWAY_HOME'] = self.tmp.name
        self.con = db.connect()
        self.con.execute("INSERT INTO repos(name, path, base) VALUES ('app', '/tmp/app', 'main')")
        self.con.execute("INSERT OR IGNORE INTO runners(name, kind, slots) VALUES ('This Mac', 'this_mac', 2)")
        self.con.execute("UPDATE agents SET signed_in = (kind = 'claude')")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def file_batch(self):
        return tickets.file_batch(self.con, 'app', [
            {'key': 'a', 'title': 'Check the camera on the phone', 'risk': 'not-low', 'hands_on': True,
             'acceptance': ['A1: the preview fills the frame on a real iPhone']},
            {'key': 'b', 'title': 'Store the frame size', 'risk': 'low', 'risk_reason': 'new column',
             'acceptance': ['A1: it round-trips. Verify: python3 -m unittest'], 'blocked_by': ['a']},
        ])

    def test_filed_hands_on_is_its_own_state_and_blocks_the_runway_ticket(self):
        a, b = self.file_batch()
        self.assertEqual(db.ticket(self.con, a)['state'], 'hands_on')
        self.assertEqual(db.ticket(self.con, a)['hands_on'], 1)
        self.assertEqual(db.ticket(self.con, b)['state'], 'queued')
        self.assertEqual(db.ticket(self.con, b)['hands_on'], 0)
        self.assertEqual(db.blockers(self.con, b), [a])

        # Both are on the board, in Up next; the hands-on one says it is the person's to do.
        rows = {t['id']: t for t in (status.ticket_json(self.con, db.ticket(self.con, x), None) for x in (a, b))}
        self.assertEqual(rows[a]['column'], 'up_next')
        self.assertTrue(rows[a]['hands_on'])
        self.assertFalse(rows[a]['done_locally'])
        self.assertIn('Yours to do', rows[a]['summary'])
        self.assertIn(f'runway done {a}', rows[a]['summary'])
        self.assertEqual(rows[a]['blocks'], [b])
        self.assertEqual(rows[b]['waits_on'], [a])

    def test_the_loop_never_starts_a_hands_on_ticket(self):
        a, b = self.file_batch()
        runner = FakeRunner(self.tmp.name)
        loop = Loop(self.con, runner=runner, github=FakeGitHub(), log=lambda *_: None)
        loop.tick()
        self.assertEqual([], runner.started)                            # b waits on a; a is not the loop's to start
        self.assertEqual(db.ticket(self.con, a)['state'], 'hands_on')

        # a done by hand: the one that waited starts on the next tick.
        db.update_ticket(self.con, a, state='done', merged_at=db.now(), merged_by='you_local')
        loop.tick()
        self.assertEqual(1, len(runner.started))
        self.assertEqual(db.ticket(self.con, b)['state'], 'building')

    def test_the_board_says_why_nothing_is_running(self):
        a, b = self.file_batch()
        db.set_meta(self.con, 'loop_pid', str(os.getpid()))             # as if the loop were running
        repo = status.snapshot(self.con)['repos'][0]
        self.assertIn(a, repo['idle_reason'] or '')
        self.assertIn('by hand', repo['idle_reason'])
        self.assertEqual(repo['idle_ticket'], a)

    def test_stats_count_a_hands_on_ticket_on_its_own(self):
        a, b = self.file_batch()
        now = db.now()
        db.update_ticket(self.con, a, state='done', merged_at=now, merged_by='you_local')
        db.update_ticket(self.con, b, state='done', merged_at=now, merged_by='gate')
        w = stats.window(self.con, 7)
        self.assertEqual((w['merged'], w['hands_off'], w['by_hand']), (1, 1, 1))
        self.assertEqual(w['hands_off_rate'], 1.0)                      # the hands-on one is not a failure
        self.assertEqual(w['by_hand_tickets'], [a])


class DoneByHandTest(unittest.TestCase):
    """The person did the work in their own session: `runway done` closes the ticket only once the work is in the
    base branch the Runway tickets build from."""

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
        self.con.execute("UPDATE agents SET signed_in = (kind = 'claude')")
        self.a, self.b = tickets.file_batch(self.con, 'app', [
            {'key': 'a', 'title': 'How the sheet feels', 'risk': 'not-low', 'hands_on': True,
             'acceptance': ['A1: the sheet settles without a bounce']},
            {'key': 'b', 'title': 'Remember the last sheet height', 'risk': 'low', 'risk_reason': 'one key',
             'acceptance': ['A1: it round-trips'], 'blocked_by': ['a']}])
        self.runner = NoTmuxRunner()

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

    def test_take_work_merge_then_done(self):
        wt, branch = take.take(self.con, self.a, runner=self.runner)
        self.assertEqual(branch, f'rw/{self.a}')

        mine = self.commit(wt, 'sheet.swift', '// settled\n', f'{self.a}: sheet', branch=branch)

        # Uncommitted work is refused.
        (Path(wt) / 'sheet.swift').write_text('// more\n')
        with self.assertRaisesRegex(db.RunwayError, 'uncommitted'):
            take.done(self.con, self.a, runner=self.runner, github=FakeGitHub())
        sh('checkout', '--', 'sheet.swift', cwd=wt)

        # Committed but not in main: refused, because the tickets waiting on it build from main.
        with self.assertRaisesRegex(db.RunwayError, 'not in main yet'):
            take.done(self.con, self.a, runner=self.runner, github=FakeGitHub())
        self.assertEqual(db.ticket(self.con, self.a)['state'], 'taken')
        self.assertEqual(db.ticket(self.con, self.b)['state'], 'queued')

        # Merged into main, as the person's own session would: now it closes.
        sh('fetch', '-q', 'origin', branch, cwd=self.clone)
        sh('-c', 'user.name=t', '-c', 'user.email=t@t', 'merge', '-q', '--no-edit', 'FETCH_HEAD', cwd=self.clone)
        sh('push', '-q', 'origin', 'main', cwd=self.clone)
        said = take.done(self.con, self.a, note='checked on the phone', runner=self.runner, github=FakeGitHub())
        self.assertIn('outside Runway', said)
        self.assertIn(self.b, said)                                     # it says what can start now
        t = db.ticket(self.con, self.a)
        self.assertEqual((t['state'], t['merged_by'], t['take_dir']), ('done', 'you_local', None))
        self.assertIn('yourself', t['note'])
        self.assertIn('checked on the phone', t['note'])
        self.assertEqual(take.done(self.con, self.a, runner=self.runner, github=FakeGitHub()),
                         f'{self.a} is already done')                   # twice is harmless
        self.assertEqual(mine, sh('rev-parse', f'refs/heads/{branch}', cwd=self.origin))

    def test_a_hands_on_ticket_with_nothing_to_merge_closes(self):
        """Work that changed no code at all: a check on a device, a look at how something feels."""
        said = take.done(self.con, self.a, note='looked at it on the phone', runner=self.runner, github=FakeGitHub())
        self.assertIn('outside Runway', said)
        self.assertEqual(db.ticket(self.con, self.a)['merged_by'], 'you_local')

    def test_it_can_still_be_given_to_runway_instead(self):
        wt, branch = take.take(self.con, self.a, runner=self.runner)
        self.commit(wt, 'sheet.swift', '// settled\n', f'{self.a}: sheet', branch=branch)
        take.give(self.con, self.a, runner=self.runner)
        self.assertEqual(db.ticket(self.con, self.a)['state'], 'queued')   # Runway reviews it like any other


if __name__ == '__main__':
    unittest.main()
