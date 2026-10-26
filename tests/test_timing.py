import os
import tempfile
import unittest

from runway import db, status, timing, tickets


class TimingTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['RUNWAY_HOME'] = self.tmp.name
        self.con = db.connect()
        self.con.execute('UPDATE agents SET signed_in=1')
        self.con.execute("INSERT INTO repos(name, path, base) VALUES ('app', '/tmp/app', 'main')")
        self.t0 = db.now() - 3600

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def file(self, key='a', **kw):
        t = {'key': key, 'title': key, 'risk': 'low', 'risk_reason': 'x', 'acceptance': ['A1']}
        t.update(kw)
        tid = tickets.file_batch(self.con, 'app', [t])[0]
        self.con.execute('UPDATE tickets SET filed_at=? WHERE id=?', (self.t0, tid))
        return tid

    def add_run(self, tid, kind, start, end=None, role=None, stage=None, stage_at=None):
        self.con.execute('INSERT INTO runs(ticket, kind, role, agent, runner, started_at, ended_at, stage, stage_at) '
                         "VALUES (?, ?, ?, 'claude', 'This Mac', ?, ?, ?, ?)",
                         (tid, kind, role, self.t0 + start, self.t0 + end if end is not None else None, stage,
                          self.t0 + stage_at if stage_at is not None else None))

    def test_a_finished_ticket_breaks_down_into_its_parts(self):
        t = self.file()
        self.add_run(t, 'build', 60, 660)                               # 10 min build, after 1 min in the queue
        self.add_run(t, 'review', 660, 960, role='code')                # two reviews side by side: 5 min, counted once
        self.add_run(t, 'review', 670, 900, role='function')
        self.con.execute("INSERT INTO stops(ticket, repo, at, reason) VALUES (?, 'app', ?, 'worker_question')",
                         (t, self.t0 + 960))                        # then 20 min waiting for the person
        self.add_run(t, 'build', 2160, 2460)                            # a 5 min fix pass
        db.update_ticket(self.con, t, state='done', merged_at=self.t0 + 2520)
        x = timing.ticket(self.con, db.ticket(self.con, t))
        self.assertEqual(x['total_seconds'], 2460)                   # first start to merge
        self.assertEqual(x['parts'], {'build': 600, 'fix': 300, 'review': 300, 'waiting_for_you': 1200,
                                      'queued': 2520 - (600 + 300 + 300 + 1200)})
        self.assertEqual([r['seconds'] for r in x['runs']], [600, 300, 230, 300])

    def test_running_up_next_and_needs_you_say_since_when(self):
        a = self.file('a')
        self.add_run(a, 'build', 100, stage='check', stage_at=700)
        db.update_ticket(self.con, a, state='checking')
        live = self.con.execute('SELECT * FROM runs WHERE ticket=? AND ended_at IS NULL', (a,)).fetchone()
        x = timing.ticket(self.con, db.ticket(self.con, a), live)
        self.assertEqual((x['stage'], x['stage_started_at'], x['started_at']), ('check', self.t0 + 700, self.t0 + 100))
        b = self.file('b', blocked_by=[a])
        db.update_ticket(self.con, a, state='done')                  # b was unblocked just now
        y = timing.ticket(self.con, db.ticket(self.con, b))
        self.assertAlmostEqual(y['waiting_since'], db.ticket(self.con, a)['updated_at'], delta=1)
        c = self.file('c')
        self.con.execute("INSERT INTO stops(ticket, repo, at, reason) VALUES (?, 'app', ?, 'worker_question')",
                         (c, self.t0 + 1800))
        db.update_ticket(self.con, c, state='needs_you')
        self.assertEqual(timing.ticket(self.con, db.ticket(self.con, c))['waiting_since'], self.t0 + 1800)
        snap = {t['id']: t for t in status.snapshot(self.con)['tickets']}
        self.assertIsNotNone(snap[c]['timing']['waiting_since'])
        self.assertEqual(snap[a]['timing']['stage'], 'check')

    def test_words(self):
        self.assertEqual([timing.words(s) for s in (45, 720, 3900, 7200, 97200)],
                         ['45 s', '12 min', '1 h 5 min', '2 h', '1 d 3 h'])
        self.assertEqual(timing.union([(0, 10), (5, 20), (30, 40)]), 30)


if __name__ == '__main__':
    unittest.main()
