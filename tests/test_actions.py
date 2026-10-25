import os
import tempfile
import unittest

from runway import actions, db, status, tickets


class FakeGitHub:
    def __init__(self):
        self.merged = []

    def pr(self, path, number):
        return {'headRefOid': 'abc123'}

    def merge(self, path, number, head, method='merge'):
        self.merged.append((number, head))


class ActionsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['RUNWAY_HOME'] = self.tmp.name
        self.con = db.connect()
        self.con.execute("INSERT INTO repos(name, path, base) VALUES ('demo', '/tmp/demo', 'main')")
        tickets.file_batch(self.con, 'demo', [{'title': 'Sign in', 'acceptance': ['A1']}])

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def ask(self, kind, **extra):
        db.update_ticket(self.con, 'T-1', state='needs_you', pr=7, question={'kind': kind, 'text': 'Which?', **extra})

    def test_go_on_merge_merges_the_head(self):
        self.ask('merge')
        gh = FakeGitHub()
        actions.answer(self.con, 'T-1', 'go', github=gh)
        self.assertEqual(gh.merged, [(7, 'abc123')])
        t = db.ticket(self.con, 'T-1')
        self.assertEqual((t['state'], t['question']), ('done', None))
        self.assertEqual(status.snapshot(self.con)['tickets'][0]['pr'], '#7 merged')

    def test_no_on_merge_with_note_is_a_fix_pass(self):
        self.ask('merge')
        actions.answer(self.con, 'T-1', 'no', note='rename the flag')
        t = db.ticket(self.con, 'T-1')
        self.assertEqual(t['state'], 'queued')
        self.assertIn('rename the flag', t['note'])

    def test_no_on_merge_alone_drops(self):
        self.ask('merge')
        actions.answer(self.con, 'T-1', 'no')
        self.assertEqual(db.ticket(self.con, 'T-1')['state'], 'dropped')

    def test_question_go_uses_the_recommendation(self):
        self.ask('question')
        actions.answer(self.con, 'T-1', 'go')
        t = db.ticket(self.con, 'T-1')
        self.assertEqual(t['state'], 'queued')
        self.assertIn('Use what you recommended', t['note'])

    def test_question_no_needs_the_answer(self):
        self.ask('question')
        with self.assertRaisesRegex(db.RunwayError, '--note'):
            actions.answer(self.con, 'T-1', 'no')
        actions.answer(self.con, 'T-1', 'no', note='ISO dates')
        self.assertIn('ISO dates', db.ticket(self.con, 'T-1')['note'])

    def test_answer_refuses_a_ticket_not_waiting(self):
        with self.assertRaisesRegex(db.RunwayError, 'not waiting'):
            actions.answer(self.con, 'T-1', 'go')

    def test_answers_are_recorded(self):
        self.ask('failed')
        actions.answer(self.con, 'T-1', 'go', note='try codex')
        row = self.con.execute('SELECT answer, note FROM answers').fetchone()
        self.assertEqual((row['answer'], row['note']), ('go', 'try codex'))

    def test_pause_and_resume(self):
        actions.pause(self.con, None, '1h')
        self.assertIsNotNone(status.paused_until(self.con))
        self.assertEqual(status.snapshot(self.con)['repos'][0]['state'], 'paused')
        actions.resume(self.con)
        self.assertIsNone(status.paused_until(self.con))
        actions.pause(self.con, 'demo')
        self.assertEqual(status.snapshot(self.con)['repos'][0]['state'], 'paused')
        with self.assertRaises(db.RunwayError):
            actions.pause(self.con, 'nowhere')

    def test_stop_and_start(self):
        actions.start_stop(self.con, 'demo', False)
        self.assertEqual(status.snapshot(self.con)['repos'][0]['state'], 'off')
        actions.start_stop(self.con, 'demo', True)
        self.assertEqual(status.snapshot(self.con)['repos'][0]['state'], 'idle')

    def test_runs_on(self):
        actions.runs_on(self.con, 'T-1', 'This Mac')
        self.assertEqual(db.ticket(self.con, 'T-1')['pinned'], 1)
        actions.runs_on(self.con, 'T-1', 'any')
        self.assertEqual(db.ticket(self.con, 'T-1')['runs_on'], None)
        actions.runs_on(self.con, 'demo', 'main')
        self.assertEqual(db.repo(self.con, 'demo')['runs_on'], 'main')


if __name__ == '__main__':
    unittest.main()
