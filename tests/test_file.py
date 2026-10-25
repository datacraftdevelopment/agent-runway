import json
import os
import tempfile
import unittest
from pathlib import Path

from runway import db, tickets


def ticket(**kw):
    t = {'title': 'Count words', 'risk': 'low', 'risk_reason': 'new module', 'acceptance': ['A1: it counts']}
    t.update(kw)
    return t


class FileTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['RUNWAY_HOME'] = self.tmp.name
        self.con = db.connect()
        self.con.execute("INSERT INTO repos(name, path, base) VALUES ('demo', '/tmp/demo', 'main')")

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def test_files_a_batch_with_blockers_by_key(self):
        ids = tickets.file_batch(self.con, 'demo', [ticket(key='a'), ticket(key='b', title='CLI', blocked_by=['a'])],
                                 filed_from='Claude Code on this Mac')
        self.assertEqual(ids, ['T-1', 'T-2'])
        self.assertEqual(db.blockers(self.con, 'T-2'), ['T-1'])
        row = db.ticket(self.con, 'T-1')
        self.assertEqual((row['state'], row['base'], row['agent'], row['risk']), ('queued', 'main', 'any', 'low'))
        ev = self.con.execute('SELECT kind, text FROM events').fetchone()
        self.assertEqual(ev['kind'], 'filed')
        self.assertIn('2 tickets from Claude Code on this Mac (T-1, T-2)', ev['text'])

    def test_low_risk_needs_a_reason(self):
        with self.assertRaisesRegex(db.RunwayError, 'risk_reason'):
            tickets.file_batch(self.con, 'demo', [ticket(risk_reason='')])

    def test_default_risk_is_not_low(self):
        tickets.file_batch(self.con, 'demo', [ticket(risk=None, risk_reason=None)])
        self.assertEqual(db.ticket(self.con, 'T-1')['risk'], 'not_low')

    def test_a_bad_ticket_files_nothing(self):
        with self.assertRaises(db.RunwayError):
            tickets.file_batch(self.con, 'demo', [ticket(), ticket(agent='gpt')])
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM tickets').fetchone()[0], 0)

    def test_unknown_blocker_and_runner_are_refused(self):
        with self.assertRaisesRegex(db.RunwayError, 'blocked_by'):
            tickets.file_batch(self.con, 'demo', [ticket(blocked_by=['T-99'])])
        with self.assertRaisesRegex(db.RunwayError, 'no runner'):
            tickets.file_batch(self.con, 'demo', [ticket(runs_on='Moon')])

    def test_runs_on_pins(self):
        tickets.file_batch(self.con, 'demo', [ticket(runs_on='This Mac')])
        self.assertEqual(db.ticket(self.con, 'T-1')['pinned'], 1)

    def test_markdown_ticket(self):
        text = Path(__file__).with_name('fixtures').joinpath('01-count-words.md').read_text()
        t = tickets.parse_markdown(text)
        self.assertEqual(t['title'], 'Count words')
        self.assertEqual(t['risk'], 'low')
        self.assertEqual(t['agent'], 'any')
        self.assertEqual(t['blocked_by'], [])
        self.assertEqual(len(t['acceptance']), 1)
        self.assertTrue(t['acceptance'][0].startswith('A1:'))

    def test_cli_reads_json_from_stdin(self):
        import io
        import sys
        from runway.cli import main
        self.con.close()
        sys.stdin = io.StringIO(json.dumps({'repo': 'demo', 'tickets': [ticket()]}))
        try:
            self.assertEqual(main(['file']), 0)
        finally:
            sys.stdin = sys.__stdin__
        self.con = db.connect()
        self.assertEqual(db.ticket(self.con, 'T-1')['filed_from'], 'a terminal')


if __name__ == '__main__':
    unittest.main()
