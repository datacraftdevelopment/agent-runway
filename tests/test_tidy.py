import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from runway import db, stats, status, take, tickets, tidy
from runway.loop import Loop


class FakeRunner:
    """Removes only what it's handed, and records it."""

    def __init__(self):
        self.removed = []

    def remove(self, repo, workdir):
        self.removed.append(str(workdir))

    def stop(self, name):
        pass


class FakeGitHub:
    def __init__(self, state='OPEN'):
        self.state = state

    def pr(self, path, number):
        return {'state': self.state}


class TidyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        os.environ['RUNWAY_HOME'] = str(self.root / 'home')
        self.con = db.connect()
        # The person's own clone, outside ~/.runway: nothing here may ever be touched.
        self.clone = self.root / 'clone'
        self.clone.mkdir()
        (self.clone / 'mine.txt').write_text('keep me')
        for name in ('app', 'site'):
            self.con.execute('INSERT INTO repos(name, path, slug, base) VALUES (?, ?, ?, ?)',
                             (name, str(self.clone), f'someone/{name}', 'main'))
        self.runner = FakeRunner()

    def tearDown(self):
        self.con.close()
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def file(self, repo='app', title='Count lines', state=None, **kw):
        t = {'title': title, 'risk': 'low', 'risk_reason': 'new module', 'acceptance': ['A1: it counts']}
        t.update(kw)
        tid = tickets.file_batch(self.con, repo, [t])[0]
        if state:
            db.update_ticket(self.con, tid, state=state)
        return tid

    def add_run(self, tid, ended=True, worktree=None):
        """A run with a folder and a worktree under ~/.runway (or where told)."""
        n = self.con.execute('SELECT COUNT(*) FROM runs WHERE ticket=?', (tid,)).fetchone()[0] + 1
        rd = db.home() / 'runs' / tid / str(n)
        rd.mkdir(parents=True)
        (rd / 'log').write_text('ran')
        wt = Path(worktree) if worktree else db.home() / 'worktrees' / db.ticket(self.con, tid)['repo'] / f'{tid}-{n}'
        wt.mkdir(parents=True, exist_ok=True)
        self.con.execute('INSERT INTO runs(ticket, kind, agent, runner, dir, run_dir, started_at, ended_at, outcome) '
                         "VALUES (?, 'build', 'claude', 'This Mac', ?, ?, ?, ?, ?)",
                         (tid, str(wt), str(rd), db.now(), db.now() if ended else None, 'done' if ended else None))
        return rd, wt

    def board(self):
        snap = status.snapshot(self.con)
        return [r['name'] for r in snap['repos']], [t['id'] for t in snap['tickets']], snap['archived']

    # ---- archive -----------------------------------------------------------------------------------------------

    def test_archive_hides_the_repo_everywhere_and_unarchive_brings_it_back(self):
        a, s = self.file('app'), self.file('site')
        db.update_ticket(self.con, a, state='done', merged_at=db.now(), merged_by='gate')
        db.update_ticket(self.con, s, state='queued')
        said = tidy.archive(self.con, 'site')
        self.assertIn('nothing was deleted', said)
        repos, ids, archived = self.board()
        self.assertEqual((repos, ids, archived), (['app'], [a], [{'name': 'site', 'tickets': 1}]))
        self.assertEqual([r['repo'] for r in stats.snapshot(self.con)['by_repo']], ['app'])
        # The loop never picks an archived repo's tickets.
        loop = Loop(self.con, runner=self.runner, github=FakeGitHub(), log=lambda *_: None)
        started = []
        loop.start = lambda t, *rest: started.append(t['id'])
        loop.dispatch()
        self.assertNotIn(s, started)
        with self.assertRaisesRegex(db.RunwayError, 'archived'):
            self.file('site')
        self.assertIn('back on the board', tidy.unarchive(self.con, 'site'))
        repos, ids, archived = self.board()
        self.assertEqual((repos, sorted(ids), archived), (['app', 'site'], sorted([a, s]), []))
        self.assertTrue(db.ticket(self.con, s))                  # nothing was deleted

    def test_archive_and_remove_refuse_while_a_ticket_runs_and_say_which(self):
        t = self.file('app', state='building')
        with self.assertRaisesRegex(db.RunwayError, f'{t} is running'):
            tidy.archive(self.con, 'app')
        with self.assertRaisesRegex(db.RunwayError, f'{t} is running'):
            tidy.remove(self.con, 'app', runner=self.runner)
        db.update_ticket(self.con, t, state='needs_you')
        self.add_run(t, ended=False)                                  # a live run counts too
        with self.assertRaisesRegex(db.RunwayError, f'{t} is running'):
            tidy.delete(self.con, t, runner=self.runner)
        self.assertEqual(self.board()[0], ['app', 'site'])

    # ---- remove ------------------------------------------------------------------------------------------------

    def test_remove_forgets_the_repo_and_never_touches_the_clone(self):
        a, b, keep = self.file('app'), self.file('app', title='Two'), self.file('site')
        db.update_ticket(self.con, a, state='done')
        rd, wt = self.add_run(a)
        outside = self.root / 'not-runways'                        # a run dir that somehow points outside ~/.runway
        self.add_run(b, worktree=outside)
        self.con.execute("INSERT INTO blockers(ticket, blocked_by) VALUES (?, ?)", (b, a))
        db.event(self.con, 'merged', 'merged it', repo='app', ticket=a)
        said = tidy.remove(self.con, 'app', runner=self.runner)
        self.assertIn('2 tickets', said)
        self.assertIn(str(self.clone), said)
        self.assertIsNone(self.con.execute("SELECT 1 FROM repos WHERE name='app'").fetchone())
        for table, col in (('tickets', 'repo'), ('events', 'repo')):
            self.assertEqual(self.con.execute(f"SELECT COUNT(*) FROM {table} WHERE {col}='app'").fetchone()[0], 0)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM runs').fetchone()[0], 0)
        self.assertEqual(self.con.execute('SELECT COUNT(*) FROM blockers').fetchone()[0], 0)
        self.assertFalse(rd.exists())
        self.assertFalse(wt.exists())
        self.assertEqual(self.runner.removed, [str(wt)])           # only Runway's own worktree went through git
        self.assertTrue(outside.exists())                          # never anything outside ~/.runway
        self.assertEqual((self.clone / 'mine.txt').read_text(), 'keep me')
        self.assertTrue(db.ticket(self.con, keep))                 # the other repo is untouched

    # ---- clear done ----------------------------------------------------------------------------------------------

    def test_clear_done_hides_done_tickets_keeps_stats_and_undoes(self):
        old, new, dropped, open_ = (self.file(title=x) for x in ('old', 'new', 'dropped', 'open'))
        day = 86400
        db.update_ticket(self.con, old, state='done', merged_at=db.now() - 10 * day, merged_by='gate')
        db.update_ticket(self.con, new, state='done', merged_at=db.now() - 1 * day, merged_by='gate')
        db.update_ticket(self.con, dropped, state='dropped')
        merged_before = stats.window(self.con, 30)['merged']
        self.assertEqual(tidy.clear_done(self.con, 'app', '7d'), [old])
        self.assertEqual(tidy.clear_done(self.con), [new, dropped])
        self.assertEqual(self.board()[1], [open_])
        self.assertEqual(stats.window(self.con, 30)['merged'], merged_before)   # still counted
        self.assertEqual(tidy.clear_done(self.con), [])
        tidy.unclear(self.con, [old, new])
        self.assertEqual(sorted(self.board()[1]), sorted([old, new, open_]))
        with self.assertRaises(db.RunwayError):
            tidy.parse_age('soon')
        self.assertEqual(tidy.parse_age('12h'), 12 * 3600)
        self.assertEqual(tidy.parse_age('2'), 2 * 86400)

    # ---- delete one ----------------------------------------------------------------------------------------------

    def test_delete_one_ticket_says_when_its_pr_is_still_open(self):
        t, other = self.file(title='Gone'), self.file(title='Stays')
        db.update_ticket(self.con, t, state='needs_you', pr=7, branch='rw/x')
        rd, wt = self.add_run(t)
        said = tidy.delete(self.con, t, github=FakeGitHub('OPEN'), runner=self.runner)
        self.assertIn('PR #7 is still open', said)
        with self.assertRaises(db.RunwayError):
            db.ticket(self.con, t)
        self.assertFalse(rd.parent.exists())
        self.assertFalse(wt.exists())
        self.assertTrue(db.ticket(self.con, other))
        u = self.file(title='Merged one')
        db.update_ticket(self.con, u, state='done', pr=8)
        self.assertNotIn('still open', tidy.delete(self.con, u, github=FakeGitHub('MERGED'), runner=self.runner))

    # ---- prompts and the main computer ------------------------------------------------------------------------

    def test_discuss_prompts_name_the_skill_and_claim_nothing(self):
        t = self.file(title='Count lines')
        db.update_ticket(self.con, t, state='needs_you', pr=3)
        self.add_run(t)
        p = take.discuss_prompt(self.con, t)
        self.assertTrue(p.startswith(f'Use the runway skill to look at ticket {t} in app'))
        self.assertIn('PR #3', p)
        self.assertIn('Don\'t take it back', p)
        self.assertEqual(db.ticket(self.con, t)['state'], 'needs_you')           # nothing taken back
        r = status.repo_prompt(self.con, 'app')
        self.assertTrue(r.startswith('Use the runway skill to look at the app repo'))
        self.assertIn(f'Needs you: {t} Count lines', r)


class CliTest(unittest.TestCase):
    """The commands as the app runs them: without --yes nothing is deleted."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = {**os.environ, 'RUNWAY_HOME': str(Path(self.tmp.name) / 'home')}
        os.environ['RUNWAY_HOME'] = self.env['RUNWAY_HOME']
        con = db.connect()
        con.execute("INSERT INTO repos(name, path, slug, base) VALUES ('app', '/tmp/nowhere', 'someone/app', 'main')")
        self.tid = tickets.file_batch(con, 'app', [{'title': 'One', 'risk': 'low', 'risk_reason': 'x',
                                                    'acceptance': ['A1: x']}])[0]
        con.close()

    def tearDown(self):
        self.tmp.cleanup()
        os.environ.pop('RUNWAY_HOME', None)

    def runway(self, *args):
        cli = Path(__file__).resolve().parent.parent / 'bin' / 'runway'
        return subprocess.run(['/usr/bin/python3', str(cli), *args], env=self.env, capture_output=True, text=True,
                              timeout=60)

    def test_remove_and_delete_need_yes_and_say_what_would_go(self):
        res = self.runway('repo', 'remove', 'app')
        self.assertEqual(res.returncode, 1)
        self.assertIn('would delete 1 ticket', res.stdout)
        self.assertIn('/tmp/nowhere', res.stdout)
        preview = json.loads(self.runway('repo', 'remove', 'app', '--json').stdout)
        self.assertEqual((preview['tickets'], preview['runs'], preview['running']), (1, 0, []))
        self.assertEqual(self.runway('delete', self.tid).returncode, 1)
        self.assertEqual(json.loads(self.runway('delete', self.tid, '--json').stdout)['title'], 'One')
        self.assertIn(self.tid, self.runway('status').stdout)                       # still there
        self.assertEqual(self.runway('delete', self.tid, '--yes').returncode, 0)
        self.assertNotIn(self.tid, self.runway('status').stdout)
        self.assertEqual(self.runway('repo', 'remove', 'app', '--yes').returncode, 0)
        self.assertEqual(json.loads(self.runway('status', '--json').stdout)['repos'], [])

    def test_archive_clear_done_and_main_computer(self):
        self.assertIn('archived app', self.runway('repo', 'archive', 'app').stdout)
        self.assertEqual(json.loads(self.runway('status', '--json').stdout)['archived'],
                         [{'name': 'app', 'tickets': 1}])
        self.assertIn('back on the board', self.runway('repo', 'unarchive', 'app').stdout)
        self.assertEqual(json.loads(self.runway('clear-done', '--json').stdout), [])
        res = self.runway('repo', 'main', 'app', 'Nowhere')
        self.assertIn('no runner', res.stderr)
        self.assertIn('main computer is This Mac', self.runway('repo', 'main', 'app', 'This Mac').stdout)
        self.assertIn('Use the runway skill', self.runway('show', self.tid, '--prompt').stdout)
        self.assertIn('the app repo', self.runway('status', 'app', '--prompt').stdout)


if __name__ == '__main__':
    unittest.main()
