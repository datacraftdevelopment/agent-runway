import json
import unittest

from runway import db, retro
from tests.test_loop import LoopTest


class RetroTest(LoopTest):
    """A3: three tickets failing the same check in 7 days file one not-low retro whose PR links all three runs."""

    def fail_check_twice(self, tid):
        for _ in range(2):
            self.loop.tick()
            self.build_done(tid)
            self.loop.tick()

    def test_three_failed_checks_file_one_retro_that_never_merges(self):
        self.runner.check_ok = False
        failing = [self.file(title=f'Ticket {n}') for n in (1, 2, 3)]
        for tid in failing[:2]:
            self.fail_check_twice(tid)
        self.assertFalse(retro.due(self.con, 'demo'))                    # two isn't enough
        self.fail_check_twice(failing[2])
        self.loop.tick()                                                  # the tick files the retro
        retros = self.con.execute("SELECT * FROM tickets WHERE kind='retro'").fetchall()
        self.assertEqual(len(retros), 1)
        r = retros[0]
        self.assertEqual((r['risk'], r['retro_reason'], r['filed_from']), ('not_low', 'check_failed_twice',
                                                                         'Runway (retro)'))
        self.assertIn('Retro: check failed twice stopped 3 tickets in 7 days', r['title'])
        for tid in failing:
            self.assertIn(f'### {tid}', r['body'])
        self.assertIn('the check failed after the build', r['body'])      # the check output
        self.assertIn('Run record:', r['body'])
        self.loop.tick()
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM tickets WHERE kind='retro'").fetchone()[0], 1)

        # The retro runs like any ticket; its PR has "Runs behind this", and the gate won't merge it.
        self.runner.check_ok = True
        rid = r['id']
        self.assertEqual(self.live_run(rid)['kind'], 'build')
        self.build_done(rid)
        self.loop.tick()
        t = db.ticket(self.con, rid)
        pr_body = self.gh.bodies[t['pr']]
        self.assertIn('## Runs behind this', pr_body)
        for tid in failing:
            self.assertIn(f'- {tid}: Ticket', pr_body)
        self.assertEqual(pr_body.count('run record'), 3)
        self.both_reviews(rid)
        self.loop.tick()
        t = db.ticket(self.con, rid)
        q = json.loads(t['question'])
        self.assertEqual((t['state'], q['kind']), ('needs_you', 'merge'))
        self.assertIn('it is a retro, which never merges on its own', q['text'])
        self.assertEqual(self.gh.merged, [])

    def test_not_low_risk_stops_never_file_a_retro(self):
        for n in range(3):
            tid = self.file(title=f'T{n}', risk='not_low', risk_reason=None)
            self.con.execute('INSERT INTO stops(ticket, repo, at, reason) VALUES (?, ?, ?, ?)',
                             (tid, 'demo', db.now(), 'not_low_risk'))
        self.assertEqual(retro.due(self.con, 'demo'), [])

    def test_threshold_from_runway_json_and_by_hand(self):
        tid = self.file(title='One')
        self.con.execute('INSERT INTO stops(ticket, repo, at, reason, detail) VALUES (?, ?, ?, ?, ?)',
                         (tid, 'demo', db.now(), 'worker_question', 'which date format?'))
        self.assertEqual(retro.due(self.con, 'demo'), [])
        self.runner.cfg['retro_threshold'] = 1
        self.loop.tick()
        self.assertEqual(self.con.execute("SELECT retro_reason FROM tickets WHERE kind='retro'").fetchone()[0],
                         'worker_question')
        with self.assertRaisesRegex(db.RunwayError, 'nothing in demo stopped'):
            retro.file(self.con, 'demo', 'sensitive_path', by_hand=True)

    def test_old_stops_dont_count(self):
        for n in range(3):
            tid = self.file(title=f'T{n}')
            self.con.execute('INSERT INTO stops(ticket, repo, at, reason) VALUES (?, ?, ?, ?)',
                             (tid, 'demo', db.now() - 8 * 86400, 'check_failed_twice'))
        self.assertEqual(retro.due(self.con, 'demo'), [])


if __name__ == '__main__':
    unittest.main()
