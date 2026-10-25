import json
import os
import tempfile
import unittest
from pathlib import Path

from runway import db, status, tickets

FIXTURE = Path(__file__).resolve().parent.parent / 'app/Tests/RunwayCoreTests/Fixtures/sample-status.json'

# What the Swift side decodes (app/Sources/RunwayCore/Status.swift). Enum values the app accepts:
COLUMNS = {'needs_you', 'up_next', 'running', 'done'}
STAGES = {None, 'build', 'check', 'review', 'merge'}
REPO_STATES = {'running', 'idle', 'needs_you', 'paused', 'off'}


def keys(obj):
    return set(obj.keys())


class StatusShapeTest(unittest.TestCase):
    """The snapshot keeps the fixture's shape, so the app reads `runway status --json` exactly like the sample."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ['RUNWAY_HOME'] = self.tmp.name
        self.con = db.connect()
        self.con.execute("INSERT INTO repos(name, path, base) VALUES ('demo', '/tmp/demo', 'main')")
        self.con.execute("INSERT INTO setup(runner, reachable, claude, codex, github) "
                         "VALUES ('This Mac', 'yes', 'yes', 'yes', 'yes')")
        tickets.file_batch(self.con, 'demo', [
            {'key': 'a', 'title': 'Count words', 'risk': 'low', 'risk_reason': 'new module', 'acceptance': ['A1']},
            {'key': 'b', 'title': 'CLI', 'acceptance': ['A1'], 'blocked_by': ['a']},
        ])
        self.fixture = json.loads(FIXTURE.read_text())

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def test_same_keys_as_the_fixture(self):
        snap = status.snapshot(self.con)
        f = self.fixture
        self.assertEqual(keys(snap), keys(f))
        self.assertEqual(keys(snap['repos'][0]), keys(f['repos'][0]))
        self.assertEqual(keys(snap['runners'][0]), keys(f['runners'][0]))
        self.assertEqual(keys(snap['agents'][0]), keys(f['agents'][0]))
        self.assertEqual(keys(snap['setup'][0]), keys(f['setup'][0]))
        self.assertEqual(keys(snap['activity'][0]), keys(f['activity'][0]))
        # The fixture leaves out keys that are null for a ticket; the snapshot always sends them.
        fixture_ticket_keys = set().union(*(keys(t) for t in f['tickets']))
        self.assertLessEqual(fixture_ticket_keys, keys(snap['tickets'][0]))

    def test_values_the_app_accepts(self):
        snap = status.snapshot(self.con)
        self.assertEqual([t['column'] for t in snap['tickets']], ['up_next', 'up_next'])
        for t in snap['tickets']:
            self.assertIn(t['column'], COLUMNS)
            self.assertIn(t['stage'], STAGES)
        self.assertIn(snap['repos'][0]['state'], REPO_STATES)
        self.assertEqual(snap['tickets'][1]['waits_on'], ['T-1'])
        self.assertEqual(snap['repos'][0]['status_line'], 'Idle · 2 up next')
        self.assertEqual(snap['runners'][0]['name'], 'This Mac')

    def test_running_ticket_shows_stage_runner_and_elapsed(self):
        self.con.execute("UPDATE tickets SET state='building' WHERE id='T-1'")
        self.con.execute("INSERT INTO runs(ticket, kind, agent, runner, started_at) "
                         "VALUES ('T-1', 'build', 'codex', 'This Mac', ?)", (db.now() - 125,))
        snap = status.snapshot(self.con)
        t1 = snap['tickets'][0]
        self.assertEqual((t1['column'], t1['stage'], t1['runs_on']), ('running', 'build', 'This Mac'))
        self.assertGreaterEqual(t1['elapsed'], 125)
        self.assertEqual(snap['runners'][0]['slots_used'], 1)
        self.assertEqual(snap['repos'][0]['state'], 'running')

    def test_needs_you_carries_the_question(self):
        db.update_ticket(self.con, 'T-1', state='needs_you',
                         question={'text': 'Merge PR #4?', 'short': 'Merge count words?', 'go_label': 'Merge'})
        t1 = status.snapshot(self.con)['tickets'][0]
        self.assertEqual(t1['column'], 'needs_you')
        self.assertEqual(t1['question'], {'text': 'Merge PR #4?', 'short': 'Merge count words?',
                                          'go_label': 'Merge', 'no_label': 'No'})

    def test_resting_agent(self):
        self.con.execute("UPDATE agents SET resting_until=? WHERE kind='claude'", (db.now() + 600,))
        agents = {a['kind']: a['resting_until'] for a in status.snapshot(self.con)['agents']}
        self.assertIsNotNone(agents['claude'])
        self.assertIsNone(agents['codex'])


if __name__ == '__main__':
    unittest.main()
