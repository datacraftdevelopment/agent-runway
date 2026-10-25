import json
import os
import tempfile
import unittest

from runway import db, stats, tickets


class StatsTest(unittest.TestCase):
    """Hands-off: the gate merged it, nobody answered a question about it, it was never taken back."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['RUNWAY_HOME'] = self.tmp.name
        self.con = db.connect()
        for repo in ('app', 'site'):
            self.con.execute('INSERT INTO repos(name, path, base) VALUES (?, ?, ?)', (repo, f'/tmp/{repo}', 'main'))

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def ticket(self, repo='app', minutes=10, merged_by='gate', days_ago=1, **extra):
        tid = tickets.file_batch(self.con, repo, [{'title': 'x', 'acceptance': ['A1']}])[0]
        merged = db.now() - days_ago * 86400
        db.update_ticket(self.con, tid, state='done', merged_by=merged_by, merged_at=merged,
                         filed_at=merged - minutes * 60, **extra)
        return tid

    def add_run(self, tid, agent, usd=None, tin=1000, tout=100):
        self.con.execute('INSERT INTO runs(ticket, kind, agent, runner, started_at, ended_at, outcome, tokens_in, '
                         'tokens_out, cost_usd) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                         (tid, 'build', agent, 'This Mac', 0, 1, 'done', tin, tout, usd))

    def test_hands_off_rate_and_cycle_times(self):
        a = self.ticket(minutes=10)
        b = self.ticket(minutes=30)
        c = self.ticket(minutes=90, merged_by='you')              # Joe merged it
        d = self.ticket(minutes=50)
        self.con.execute("INSERT INTO answers(ticket, answer, at) VALUES (?, 'go', 0)", (d,))   # Joe answered
        e = self.ticket(minutes=40, taken=1)                      # taken back
        w = stats.window(self.con, 7)
        self.assertEqual((w['merged'], w['hands_off'], w['hands_off_rate']), (5, 2, 0.4))
        self.assertEqual(w['hands_off_tickets'], [a, b])
        self.assertEqual(sorted(w['other_tickets']), sorted([c, d, e]))
        self.assertEqual(w['cycle_minutes'], {'hands_off': 20.0, 'rest': 50.0})

    def test_windows_and_repos(self):
        self.ticket(days_ago=2)
        self.ticket(days_ago=20)
        self.ticket(repo='site', days_ago=2)
        self.assertEqual(stats.window(self.con, 7)['merged'], 2)
        self.assertEqual(stats.window(self.con, 30)['merged'], 3)
        self.assertEqual(stats.window(self.con, 30, 'site')['merged'], 1)
        snap = stats.snapshot(self.con)
        self.assertEqual(snap['windows'], [7, 30])
        self.assertEqual([s['repo'] for s in snap['by_repo']], ['app', 'site'])
        self.assertEqual([w['days'] for w in snap['all']['windows']], [7, 30])

    def test_cost_never_estimates_codex(self):
        a, b = self.ticket(), self.ticket()
        self.add_run(a, 'claude', usd=0.5)
        self.add_run(a, 'codex')
        self.add_run(b, 'claude', usd=1.5)
        self.add_run(b, 'codex', tin=3000)
        cost = stats.window(self.con, 7)['cost_per_ticket']
        self.assertEqual(cost['median_usd'], 1.0)
        by = {x['agent']: x for x in cost['by_agent']}
        self.assertEqual(by['claude']['median_usd'], 1.0)
        self.assertIsNone(by['codex']['median_usd'])              # Codex reports tokens only
        self.assertEqual(by['codex']['median_tokens'], 2100)

    def test_where_it_stopped_and_waiting(self):
        tid = tickets.file_batch(self.con, 'app', [{'title': 'Sign in', 'acceptance': ['A1']}])[0]
        for reason in ('not_low_risk', 'code_review_failed_twice', 'not_low_risk'):
            self.con.execute('INSERT INTO stops(ticket, repo, at, reason) VALUES (?, ?, ?, ?)',
                             (tid, 'app', db.now(), reason))
        db.update_ticket(self.con, tid, state='needs_you', question={'kind': 'merge', 'reason': 'not_low_risk'})
        w = stats.window(self.con, 7)
        self.assertEqual([(s['label'], s['count']) for s in w['stopped']],
                         [('not low risk', 2), ('code review failed twice', 1)])
        self.assertEqual(stats.waiting(self.con), [{'id': tid, 'repo': 'app', 'title': 'Sign in',
                                                     'reason': 'not_low_risk', 'label': 'not low risk'}])

    def test_backfill_from_an_older_database(self):
        """A version-3 database: merges and stops come back from the event log."""
        tid = tickets.file_batch(self.con, 'app', [{'title': 'x', 'acceptance': ['A1']}])[0]
        db.update_ticket(self.con, tid, state='done')
        db.event(self.con, 'merged', f'{tid} PR #1 (low risk, checks green)', repo='app', ticket=tid)
        db.event(self.con, 'needs_you', f'{tid} waits for your merge: it is not low risk', repo='app', ticket=tid)
        self.con.execute('UPDATE tickets SET merged_at=NULL, merged_by=NULL')
        self.con.execute('DELETE FROM stops')
        db.backfill_v4(self.con)
        t = db.ticket(self.con, tid)
        self.assertEqual(t['merged_by'], 'gate')
        self.assertEqual(self.con.execute('SELECT reason FROM stops').fetchone()[0], 'not_low_risk')

    def test_cli_json(self):
        import io
        import sys
        from contextlib import redirect_stdout
        from runway.cli import main
        self.ticket()
        self.con.close()
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.assertEqual(main(['stats', '--json', '--days', '7']), 0)
        self.con = db.connect()
        snap = json.loads(buf.getvalue())
        self.assertEqual(snap['all']['windows'][0]['hands_off'], 1)


if __name__ == '__main__':
    unittest.main()
