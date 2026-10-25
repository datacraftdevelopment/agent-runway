"""The loop: a plain script, not an agent. Each tick reads the database fresh, does the mechanical steps, writes the
database and returns. Stop it at any point and start it again; the database is the state, and runs already started
keep going in tmux and are picked up on the next tick.

One tick:
  1. finish what ended: read each finished run's outcome; commit, check, push and open the PR for a build, record the
     verdict for a review; a usage limit rests that agent and puts the ticket back without spending its fix pass.
  2. gate what passed review: merge on its own only when the gate says so, else ask the person.
  3. start what the free slots allow: builds for ready tickets, reviews for built ones (by the other engine when
     there is one, else by the same engine in a fresh session).
"""

import fcntl
import json
import os
import signal
import sys
import time
from pathlib import Path

from . import db, gate, limits, retro, worker
from .github import GitHub
from .runner import LocalRunner
from .ssh import SSHRunner

MAX_RUN = 60 * 60          # a run still going after an hour is stopped and counts as failed
FIX_PASSES = 1             # a failed build or review gets one fix pass before it asks the person
CHECK_GRACE = 5 * 60       # how long after a push "no checks yet" means CI hasn't started
NAMES = {'claude': 'Claude Code', 'codex': 'Codex'}


class Loop:
    def __init__(self, con, runner=None, github=None, log=print, ssh=SSHRunner):
        self.con = con
        self.runner = runner or LocalRunner()   # This Mac; also reads runway.json from the local clones
        self.github = github or GitHub()
        self.log = log
        self.ssh = ssh                          # host -> a runner for that Mac (tests pass a fake)
        self.remotes = {}

    def runner_for(self, name):
        """The runner a run started on (or will start on), from its row in the runners table."""
        row = self.con.execute('SELECT * FROM runners WHERE name=?', (name,)).fetchone() if name else None
        if not row or row['kind'] != 'ssh_mac':
            return self.runner
        if not row['host']:
            raise db.RunwayError(f'{name} has no host to reach it over ssh')
        if row['host'] not in self.remotes:
            self.remotes[row['host']] = self.ssh(row['host'])
        return self.remotes[row['host']]

    # ---- the tick ----------------------------------------------------------------------------------------------

    def tick(self):
        for run in self.con.execute('SELECT * FROM runs WHERE ended_at IS NULL ORDER BY id').fetchall():
            self.settle(run)
        for t in self.con.execute("SELECT * FROM tickets WHERE state='merging' ORDER BY filed_at").fetchall():
            self.try_gate(t)
        for tid in retro.check(self.con, self.runner.config):
            self.log(f'filed retro {tid}')
        self.dispatch()
        db.set_meta(self.con, 'loop_at', db.now())

    # ---- 1. finishing runs -------------------------------------------------------------------------------------

    def settle(self, run):
        overdue = db.now() - run['started_at'] > MAX_RUN
        runner = self.runner_for(run['runner'])
        if runner.alive(run['tmux']) and not overdue:
            return
        if overdue:
            runner.stop(run['tmux'])
        t = db.ticket(self.con, run['ticket'])
        run_dir = db.run_dir(self.con, run)
        if hasattr(runner, 'collect'):
            runner.collect(run_dir)             # a run on another Mac: bring its folder back first
        log_text = read(run_dir / 'log')
        if run['agent'] == 'codex' and not run['session_id']:
            self.con.execute('UPDATE runs SET session_id=? WHERE id=?', (worker.codex_session(log_text), run['id']))
        until = limits.limit_from(log_text)
        if until:
            self.end(run, 'limited')
            limits.rest(self.con, run['agent'], until, 'usage limit', ticket=t['id'], repo=t['repo'])
            if run['kind'] == 'build':
                db.update_ticket(self.con, t['id'], state='queued', stage=None)  # the fix pass isn't spent
            return
        if overdue:
            self.end(run, 'failed')
            return self.failed(t, f'the {run["kind"]} ran past {MAX_RUN // 60} minutes and was stopped')
        if run['kind'] == 'build':
            self.settle_build(t, run, run_dir)
        else:
            self.settle_review(t, run, run_dir)

    def settle_build(self, t, run, run_dir):
        repo = db.repo(self.con, t['repo'])
        outcome = read_json(run_dir / 'outcome.json')
        status = outcome.get('status')
        summary = (outcome.get('summary') or '').strip()
        if status == 'needs_you':
            self.end(run, 'needs_you')
            q = outcome.get('question') or 'The worker stopped with a question.'
            rec = outcome.get('recommended')
            text = q + (f' Recommended: {rec}' if rec else '')
            return self.ask(t, 'question', text, short=shorten(q),
                            go_label='Use recommended' if rec else 'Go', no_label='Answer differently',
                            log=f'{t["id"]} asked: {shorten(q, 80)}', reason='worker_question')
        if status != 'done':
            self.end(run, 'failed')
            why = summary or f'the worker ended without an outcome (exit {read(run_dir / "exit").strip() or "?"})'
            return self.failed(t, why)
        self.stage(run, 'commit')
        runner = self.runner_for(run['runner'])
        sha = runner.commit(run['dir'], f'{t["id"]}: {t["title"]}')
        if not sha and t['taken']:
            # Taken back and given back: the person's commits are the work; carry on with them.
            sha = runner.head(run['dir'])
        if not sha:
            self.end(run, 'failed')
            return self.failed(t, 'the worker said done but changed nothing')
        db.update_ticket(self.con, t['id'], state='checking', stage='check', sha=sha)
        self.stage(run, 'check')
        cfg = self.runner.config(repo)
        ok, output = runner.check(run['dir'], check_command(repo, cfg))
        if not ok:
            self.end(run, 'failed')
            return self.failed(t, f'the check failed after the build: {output[-600:]}', reason='check')
        branch = t['branch'] or f'rw/{t["id"]}'
        self.stage(run, 'push')
        runner.push(run['dir'], branch)
        self.end(run, 'done', sha=sha)
        pr = t['pr']
        if not pr:
            body = (f'Runway ticket {t["id"]}, built by {NAMES[run["agent"]]} on {run["runner"]}.\n\n'
                    f'{t["body"]}\n\n## Acceptance\n\n{worker.acceptance_lines(t)}\n\n## Worker summary\n\n{summary}')
            if t['kind'] == 'retro':
                body += '\n\n' + retro.runs_behind_section(json.loads(t['retro_runs'] or '[]'))
            pr = self.github.create_pr(repo['path'], t['base'], branch, f'{t["id"]}: {t["title"]}', body)
        db.update_ticket(self.con, t['id'], state='reviewing', stage='review', sha=sha, branch=branch, pr=pr,
                         review=None, function_review=None, note=None)
        self.stage(run, 'reviews')
        db.event(self.con, 'start', f'{t["id"]} built by {NAMES[run["agent"]]}, check passed; PR #{pr}',
                 repo=t['repo'], ticket=t['id'])

    def settle_review(self, t, run, run_dir):
        """One of the two reviews ended. Both must pass on the same head commit for the gate; either one failing
        stops the other and spends the fix pass."""
        role = run['role'] or 'code'
        label = {'code': 'Code review', 'function': 'Function review'}[role]
        verdict = read_json(run_dir / 'review.json')
        name = NAMES[run['agent']]
        v = (verdict.get('verdict') or '').lower()
        if v not in ('pass', 'fail'):
            self.end(run, 'failed')
            self.stop_reviews(t, but=run['id'])
            return self.failed(t, f'{name} ended its {label.lower()} without a verdict', reason=f'{role}_review')
        findings = list(verdict.get('findings') or [])
        if role == 'function':
            findings = worker.function_findings(verdict) + findings
            if findings:
                v = 'fail'
        if not str(verdict.get('sha') or '').startswith((run['sha'] or 'x')[:7]) or run['sha'] != t['sha']:
            v = 'fail'
            findings.append('the verdict is not for the commit under review')
        raised = (verdict.get('risk') or '').replace('-', '_') == 'not_low' and t['risk'] == 'low'
        builder = self.con.execute("SELECT agent FROM runs WHERE ticket=? AND kind='build' AND outcome='done' "
                                   "ORDER BY id DESC LIMIT 1", (t['id'],)).fetchone()
        same = builder is not None and builder['agent'] == run['agent']
        text = f'{name}{" (fresh session)" if same else ""}: {v}' + (', risk raised' if raised else '')
        self.end(run, v, sha=run['sha'])
        db.event(self.con, 'review', f'{t["id"]} {label.lower()} by {name}: {v} on {run["sha"][:7]}'
                 + (' (risk raised)' if raised else ''), repo=t['repo'], ticket=t['id'])
        self.keep_review(t, role, verdict, text)
        fields = {'review' if role == 'code' else 'function_review': text}
        if raised:
            fields['risk'] = 'not_low'
        if v == 'fail':
            db.update_ticket(self.con, t['id'], **fields)
            self.stop_reviews(t, but=run['id'])
            notes = '\n'.join(f'- {f}' for f in findings) or (verdict.get('summary') or 'no findings given')
            return self.failed(db.ticket(self.con, t['id']), f'{name} failed the {label.lower()}:\n{notes}',
                               reason=f'{role}_review')
        db.update_ticket(self.con, t['id'], **fields)
        t = db.ticket(self.con, t['id'])
        if all(self.passed(t, r) for r in worker.ROLES):
            db.update_ticket(self.con, t['id'], state='merging', stage='merge')
            return self.try_gate(db.ticket(self.con, t['id']))

    def keep_review(self, t, role, verdict, text):
        """Both verdicts, with their notes, beside the build they judged: <build run>/reviews/<role>.json."""
        build = self.con.execute("SELECT * FROM runs WHERE ticket=? AND kind='build' AND sha=? ORDER BY id DESC "
                                 "LIMIT 1", (t['id'], t['sha'])).fetchone()
        if build:
            folder = db.run_dir(self.con, build) / 'reviews'
            folder.mkdir(exist_ok=True)
            (folder / f'{role}.json').write_text(json.dumps(dict(verdict, recorded=text), indent=2))

    def passed(self, t, role):
        """Whether this role's latest review of the ticket's current head commit passed."""
        row = self.con.execute("SELECT outcome FROM runs WHERE ticket=? AND kind='review' AND role=? AND sha=? "
                               "AND ended_at IS NOT NULL ORDER BY id DESC LIMIT 1", (t['id'], role, t['sha'])).fetchone()
        return bool(row and row['outcome'] == 'pass')

    def stop_reviews(self, t, but=None):
        for r in self.con.execute("SELECT * FROM runs WHERE ticket=? AND kind='review' AND ended_at IS NULL AND id != ?",
                                  (t['id'], but or -1)).fetchall():
            self.runner_for(r['runner']).stop(r['tmux'])
            self.end(r, 'cancelled')

    def end(self, run, outcome, sha=None):
        run_dir = db.run_dir(self.con, run)
        tin, tout, cost = worker.usage(run['agent'], read(run_dir / 'log'))
        session = run['session_id'] or (worker.codex_session(read(run_dir / 'log')) if run['agent'] == 'codex' else None)
        transcript = worker.link_transcript(run['agent'], session, run_dir)
        self.con.execute('UPDATE runs SET ended_at=?, outcome=?, sha=COALESCE(?, sha), tokens_in=?, tokens_out=?, '
                         'cost_usd=?, session_id=COALESCE(session_id, ?), transcript=? WHERE id=?',
                         (db.now(), outcome, sha, tin, tout, cost, session, transcript, run['id']))

    def stage(self, run, stage):
        self.con.execute('UPDATE runs SET stage=? WHERE id=?', (stage, run['id']))

    def failed(self, t, why, reason='build'):
        """A fix pass if one is left, else the person. `reason` is why it stopped, for the stats."""
        if t['fix_passes'] < FIX_PASSES:
            db.update_ticket(self.con, t['id'], state='queued', stage=None, fix_passes=t['fix_passes'] + 1,
                             note=f'This is a fix pass. Last time: {why}')
            db.event(self.con, 'failed', f'{t["id"]}: {shorten(why, 140)}; it gets a fix pass',
                     repo=t['repo'], ticket=t['id'])
            self.log(f'{t["id"]} failed, fix pass: {shorten(why, 100)}')
            return
        self.ask(t, 'failed', f'It failed again: {why}', short=f'{t["id"]} failed twice',
                 go_label='Try again', no_label='Drop it', log=f'{t["id"]} failed twice',
                 reason=f'{reason}_failed_twice')

    def ask(self, t, kind, text, short, go_label, no_label, log, reason=None):
        last = self.con.execute('SELECT id FROM runs WHERE ticket=? ORDER BY id DESC LIMIT 1', (t['id'],)).fetchone()
        self.con.execute('INSERT INTO stops(ticket, repo, at, reason, run, detail) VALUES (?, ?, ?, ?, ?, ?)',
                         (t['id'], t['repo'], db.now(), reason or kind, last['id'] if last else None, text[:4000]))
        db.update_ticket(self.con, t['id'], state='needs_you', stage=None,
                         question={'kind': kind, 'text': text, 'short': short, 'reason': reason or kind,
                                   'go_label': go_label, 'no_label': no_label})
        db.event(self.con, 'needs_you', log, repo=t['repo'], ticket=t['id'])
        self.log(f'needs you: {log}')

    # ---- 2. the gate -------------------------------------------------------------------------------------------

    def try_gate(self, t):
        repo = db.repo(self.con, t['repo'])
        pr = self.github.pr(repo['path'], t['pr'])
        checks = self.github.checks(repo['path'], t['pr'])
        last = self.con.execute("SELECT ended_at FROM runs WHERE ticket=? AND kind='build' ORDER BY id DESC LIMIT 1",
                                (t['id'],)).fetchone()
        fresh = bool(last and last['ended_at'] and db.now() - last['ended_at'] < CHECK_GRACE)
        verdict, reasons = gate.evaluate(t, pr, checks, self.runner.config(repo), fresh=fresh)
        if verdict == 'wait':
            return
        if verdict == 'merged':
            db.update_ticket(self.con, t['id'], state='done', stage=None, note='Merged outside Runway.',
                             merged_at=db.now(), merged_by='outside')
            return self.cleanup(t)
        if verdict == 'merge':
            self.github.merge(repo['path'], t['pr'], pr['headRefOid'], self.runner.config(repo).get('merge_method',
                                                                                                      'merge'))
            db.update_ticket(self.con, t['id'], state='done', stage=None, merged_at=db.now(), merged_by='gate',
                             note='Merged on its own: low risk, both reviews passed, checks green.')
            db.event(self.con, 'merged', f'{t["id"]} PR #{t["pr"]} (low risk, checks green)', repo=t['repo'],
                     ticket=t['id'])
            self.log(f'merged {t["id"]} (PR #{t["pr"]})')
            return self.cleanup(t)
        why = '; '.join(reasons)
        self.ask(t, 'merge', f'The build and both reviews passed, but {why}, so it doesn\'t merge on its own. '
                 f'Merge PR #{t["pr"]}?', short=f'Merge {t["title"][:40]}?', go_label='Merge', no_label='No',
                 log=f'{t["id"]} waits for your merge: {why}', reason=gate.stop_reason(reasons))

    def cleanup(self, t):
        repo = db.repo(self.con, t['repo'])
        for r in self.con.execute('SELECT dir, runner FROM runs WHERE ticket=? AND dir IS NOT NULL', (t['id'],)):
            self.runner_for(r['runner']).remove(repo, r['dir'])

    # ---- 3. starting work --------------------------------------------------------------------------------------

    def dispatch(self):
        pause = db.meta(self.con, 'paused_until')
        if pause and float(pause) > db.now():
            return
        free = self.free_slots()
        ready = self.con.execute(
            "SELECT t.* FROM tickets t JOIN repos r ON r.name = t.repo "
            "WHERE r.active = 1 AND (r.paused_until IS NULL OR r.paused_until < ?) "
            "AND t.state IN ('queued', 'reviewing') "
            "ORDER BY t.state = 'reviewing' DESC, t.filed_at, CAST(SUBSTR(t.id, 3) AS INTEGER)",
            (db.now(),)).fetchall()
        for t in ready:
            if t['state'] == 'queued':
                if self.blocked(t):
                    continue
                jobs = [None]
            else:
                jobs = self.reviews_due(t)
            for role in jobs:
                runner = self.pick_runner(t, free)
                if not runner:
                    break
                agent = self.pick_agent(t, role)
                if not agent:
                    continue
                try:
                    self.start(t, runner, agent, role)
                except db.RunwayError as e:
                    self.failed(t, f'could not start: {e}')
                    break
                free[runner] -= 1

    def reviews_due(self, t):
        """The review roles a built ticket still needs: no verdict on its head commit yet and none running."""
        due = []
        for role in worker.ROLES:
            live = self.con.execute("SELECT 1 FROM runs WHERE ticket=? AND kind='review' AND role=? AND ended_at IS NULL",
                                    (t['id'], role)).fetchone()
            done = self.con.execute("SELECT 1 FROM runs WHERE ticket=? AND kind='review' AND role=? AND sha=? "
                                    "AND outcome IN ('pass', 'fail')", (t['id'], role, t['sha'])).fetchone()
            if not live and not done:
                due.append(role)
        return due

    def free_slots(self):
        used = {r['runner']: r['n'] for r in self.con.execute(
            'SELECT runner, COUNT(*) n FROM runs WHERE ended_at IS NULL GROUP BY runner')}
        # This Mac and SSH Macs run tickets; cloud comes with its runner.
        return {r['name']: r['slots'] - used.get(r['name'], 0) for r in self.con.execute(
            "SELECT * FROM runners WHERE (kind='this_mac' OR (kind='ssh_mac' AND host IS NOT NULL)) AND state='online' "
            "AND (paused_until IS NULL OR paused_until < ?)", (db.now(),))}

    def blocked(self, t):
        return any(self.con.execute("SELECT 1 FROM tickets WHERE id=? AND state != 'done'", (b,)).fetchone()
                   for b in db.blockers(self.con, t['id']))

    def pick_runner(self, t, free):
        repo = db.repo(self.con, t['repo'])
        if t['runs_on']:
            wanted = [t['runs_on']]
        elif repo['runs_on'] == 'main':
            wanted = [repo['main_computer']]
        else:
            wanted = sorted(free, key=lambda n: -free[n])
        return next((n for n in wanted if free.get(n, 0) > 0), None)

    def pick_agent(self, t, role=None):
        """Builds: the ticket's agent, or for Any whichever engine is available (the less busy first).

        Reviews (Joe, 2026-10-25): two fresh sessions, each with its own prompt and none of the builder's context.
        The code review prefers the other engine from the builder, the function review takes whichever is less busy;
        with one engine both run on it, and both count toward the gate. An engine resting until its usage limit
        resets starts nothing: the ticket waits, it doesn't fail."""
        busy = {r['agent']: r['n'] for r in self.con.execute(
            'SELECT agent, COUNT(*) n FROM runs WHERE ended_at IS NULL GROUP BY agent')}
        if role:
            built = self.con.execute("SELECT agent FROM runs WHERE ticket=? AND kind='build' AND outcome='done' "
                                     "ORDER BY id DESC LIMIT 1", (t['id'],)).fetchone()
            builder = built['agent'] if built else 'claude'
            other = 'codex' if builder == 'claude' else 'claude'
            order = (other, builder) if role == 'code' else sorted((builder, other), key=lambda a: busy.get(a, 0))
            return next((a for a in order if limits.available(self.con, a)), None)
        if t['agent'] != 'any':
            return t['agent'] if limits.available(self.con, t['agent']) else None
        choices = [a for a in ('claude', 'codex') if limits.available(self.con, a)]
        return min(choices, key=lambda a: busy.get(a, 0)) if choices else None

    def start(self, t, runner_name, agent, role=None):
        repo = db.repo(self.con, t['repo'])
        runner = self.runner_for(runner_name)
        kind = 'review' if t['state'] == 'reviewing' else 'build'
        cur = self.con.execute('INSERT INTO runs(ticket, kind, role, agent, runner, started_at) '
                               'VALUES (?, ?, ?, ?, ?, ?)',
                               (t['id'], kind, role if kind == 'review' else None, agent, runner_name, db.now()))
        run_id = cur.lastrowid
        n = self.con.execute('SELECT COUNT(*) FROM runs WHERE ticket=?', (t['id'],)).fetchone()[0]
        run_dir = db.home() / 'runs' / t['id'] / str(n)
        run_dir.mkdir(parents=True, exist_ok=True)
        self.con.execute('UPDATE runs SET run_dir=?, stage=? WHERE id=?',
                         (str(run_dir), 'build' if kind == 'build' else f'{role or "code"} review', run_id))
        cfg = self.runner.config(repo)
        check = check_command(repo, cfg)
        commands = [check] + list(cfg.get('worker_commands', []))
        branch = t['branch'] or f'rw/{t["id"]}'
        try:
            if kind == 'build':
                # A fix pass carries on from the pushed branch; a first build starts from the base.
                # A fix pass, or a ticket given back after a take back, carries on from the pushed branch (and the
                # person's commits on it); a first build starts from the base.
                carry_on = (t['fix_passes'] or t['taken']) and runner.has_ref(repo, f'origin/{branch}')
                start_ref = f'origin/{branch}' if carry_on else f'origin/{t["base"]}'
                # Earlier runs' worktrees still hold the ticket's branch, and git won't reset a branch checked out
                # elsewhere, so a fix pass clears them first.
                for old in self.con.execute('SELECT dir, runner FROM runs WHERE ticket=? AND id != ? AND dir IS NOT NULL '
                                            'AND ended_at IS NOT NULL', (t['id'], run_id)).fetchall():
                    self.runner_for(old['runner']).remove(repo, old['dir'])
                wt = runner.worktree(repo, t['id'], run_id, start_ref, branch=branch)
                # The base commit, for head-to-head re-runs from the same starting point.
                self.con.execute('UPDATE runs SET base_sha=? WHERE id=?',
                                 (runner.rev(repo, f'origin/{t["base"]}'), run_id))
                prompt = worker.build_prompt(t, repo['name'], start_ref, check, run_dir / 'outcome.json', commands)
            else:
                wt = runner.worktree(repo, t['id'], run_id, t['sha'])
                prompt = worker.review_prompt(t, repo['name'], t['sha'], f'origin/{t["base"]}', check,
                                              run_dir / 'review.json', commands, role=role or 'code')
        except db.RunwayError:
            self.con.execute("UPDATE runs SET ended_at=?, outcome='failed' WHERE id=?", (db.now(), run_id))
            raise
        (run_dir / 'prompt.md').write_text(prompt)
        session = worker.new_session_id() if agent == 'claude' else None
        name = f'rw-{t["id"]}-{run_id}'
        line = worker.command(agent, run_dir / 'prompt.md', run_dir, wt, commands, session_id=session)
        runner.start(name, wt, line)
        self.con.execute('UPDATE runs SET dir=?, tmux=?, session_id=?, sha=?, branch=? WHERE id=?',
                         (str(wt), name, session, t['sha'] if kind == 'review' else None,
                          branch if kind == 'build' else None, run_id))
        if kind == 'build':
            db.update_ticket(self.con, t['id'], state='building', stage='build', branch=branch)
        where = 'in the cloud' if runner_name == 'Cloud' else f'on {runner_name}'
        what = (f'{t["id"]} {role or "code"} review by {NAMES[agent]}' if kind == 'review'
                else f'{t["id"]} {where} with {NAMES[agent]}')
        db.event(self.con, 'start' if kind == 'build' else 'review', what, repo=t['repo'], ticket=t['id'])
        self.log(f'started {what}')


def check_command(repo, cfg):
    """runway.json's check_cmd (as the base branch has it) wins; else the one given when the repo was added."""
    return cfg.get('check_cmd') or (repo['check_cmd'] if 'check_cmd' in repo.keys() else None)


def read(path):
    try:
        return Path(path).read_text(errors='replace')
    except OSError:
        return ''


def read_json(path):
    try:
        data = json.loads(read(path) or '{}')
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def shorten(text, n=60):
    text = ' '.join((text or '').split())
    return text if len(text) <= n else text[:n - 1] + '…'


# ---- running it ----------------------------------------------------------------------------------------------------

def run_forever(every=15, once=False, parent=None, log=print):
    """`runway loop`. One loop at a time (a lock file); with --parent-pid it stops when the app that started it goes."""
    lock = open(db.home() / 'loop.lock', 'w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log('another runway loop is already running')
        return 1
    lock.write(str(os.getpid()))
    lock.flush()
    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append(True))
    con = db.connect()
    db.set_meta(con, 'loop_pid', os.getpid())
    loop = Loop(con, log=log)
    try:
        while not stop:
            try:
                loop.tick()
            except Exception as e:  # one bad tick never kills the loop; it says so and tries again
                db.event(con, 'failed', f'a loop tick stopped: {shorten(str(e), 200)}')
                log(f'tick failed: {e}')
            if once:
                break
            for _ in range(every):
                if stop or (parent and not alive(parent)):
                    stop.append(True)
                    break
                time.sleep(1)
    finally:
        db.set_meta(con, 'loop_pid', None)
        con.close()
    return 0


def alive(pid):
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


if __name__ == '__main__':
    sys.exit(run_forever())
