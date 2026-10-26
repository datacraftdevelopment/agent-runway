import fcntl
import os
import tempfile
import threading
import time
import unittest

from runway import db, loop, status, tickets


class WhyIdleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['RUNWAY_HOME'] = self.tmp.name
        self.con = db.connect()
        self.con.execute('UPDATE agents SET signed_in=1')
        self.con.execute("INSERT INTO repos(name, path, base) VALUES ('handstand-log', '/tmp/h', 'main')")
        db.set_meta(self.con, 'loop_pid', os.getpid())                  # a loop that is alive

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def file(self, key, blocked_by=(), **kw):
        t = {'key': key, 'title': key, 'risk': 'low', 'risk_reason': 'x', 'acceptance': ['A1'],
             'blocked_by': list(blocked_by)}
        t.update(kw)
        return tickets.file_batch(self.con, 'handstand-log', [t])[0]

    def repo(self):
        snap = status.snapshot(self.con)
        r = snap['repos'][0]
        return r['idle_reason'], r['idle_ticket']

    def joes_board(self):
        """handstand-log on 26 Oct: T-4 needs you; T-5 and T-7 wait on it, T-6 on T-5, T-8 on T-5 and T-7."""
        a = self.file('a')
        b, d = self.file('b', [a]), self.file('d', [a])
        self.file('c', [b])
        self.file('e', [b, d])
        db.update_ticket(self.con, a, state='needs_you')
        return a

    def test_everything_waits_on_one_ticket_that_needs_you(self):
        a = self.joes_board()
        self.assertEqual(self.repo(), (f'Nothing can run: 4 tickets wait on {a}, which needs you', a))

    def test_nothing_to_say_while_something_runs_or_one_is_ready(self):
        a = self.joes_board()
        db.update_ticket(self.con, a, state='building')
        self.assertEqual(self.repo(), (None, None))
        db.update_ticket(self.con, a, state='done')
        self.assertEqual(self.repo(), (None, None))                    # T-5 and T-7 are ready: the next tick starts them

    def test_waiting_for_room_paused_stopped_and_no_loop(self):
        a = self.file('a')
        self.con.execute('UPDATE tickets SET hold=? WHERE id=?', ('waiting: This Mac is busy (CPU 95% used, limit 85%)', a))
        self.assertEqual(self.repo(), ('Nothing can run: 1 ticket waits for room on This Mac', a))
        db.set_meta(self.con, 'paused_until', db.now() + 3600)
        self.assertEqual(self.repo()[0], 'Nothing can run: Runway is paused')
        db.set_meta(self.con, 'paused_until', None)
        self.con.execute("UPDATE repos SET active=0")
        self.assertEqual(self.repo()[0], 'Nothing can run: handstand-log is stopped')
        self.con.execute("UPDATE repos SET active=1")
        db.set_meta(self.con, 'loop_pid', 999999)                       # no such process
        self.assertEqual(self.repo()[0], "Nothing can run: Runway's loop isn't running")
        self.assertFalse(status.snapshot(self.con)['loop_running'])


class LoopLockTest(unittest.TestCase):
    """An app update starts the new loop while the old one is still stopping: the new one waits for it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['RUNWAY_HOME'] = self.tmp.name
        db.connect().close()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def hold_lock(self, seconds):
        held = open(db.home() / 'loop.lock', 'w')
        fcntl.flock(held, fcntl.LOCK_EX)
        threading.Timer(seconds, held.close).start()               # the old loop stops after a moment

    def test_waits_for_the_old_loop_then_runs(self):
        self.hold_lock(1.0)
        said = []
        start = time.time()
        self.assertEqual(loop.run_forever(once=True, log=said.append, wait=10), 0)        # ran its one tick
        self.assertGreaterEqual(time.time() - start, 0.9)
        self.assertNotIn('another runway loop is already running', said)

    def test_gives_up_when_the_old_loop_never_stops(self):
        self.hold_lock(5.0)
        said = []
        self.assertEqual(loop.run_forever(once=True, log=said.append, wait=1), 1)
        self.assertIn('another runway loop is already running', said)


if __name__ == '__main__':
    unittest.main()
