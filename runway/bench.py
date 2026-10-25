"""Head-to-head (Joe, 2026-10-25): re-run done tickets from their original base commit with each engine.

`runway bench <T-n>... [--agents claude,codex]` gives every engine a fresh, detached worktree at the ticket's base
commit and the same build prompt, runs them side by side, and records pass or fail against the ticket's own check
command and the Verify commands in its Acceptance lines, plus minutes, tokens and cost (dollars only where the engine
reports them). It never pushes, opens a PR or touches the ticket. It runs only when the person starts it, because it
spends both subscriptions, so it needs both engines signed in. Routing stays manual.
"""

import json
import re
import shlex
import subprocess
import time
from pathlib import Path

from . import db, worker
from .loop import check_command, read, read_json
from .runner import LocalRunner, git

ENGINES = ('claude', 'codex')
TIMEOUT = 45 * 60
VERIFY = re.compile(r'Verify:\s*`?([^`]+?)`?\s*$')


def verify_commands(t):
    """The commands an Acceptance line says to verify with ("Verify: python3 -m unittest -q")."""
    out = []
    for line in json.loads(t['acceptance'] or '[]'):
        m = VERIFY.search(line)
        if m and m.group(1).strip() not in out:
            out.append(m.group(1).strip())
    return out


def base_commit(con, t, repo):
    """The commit the ticket was first built from: recorded since version 7, else the parent of its first build."""
    first = con.execute("SELECT * FROM runs WHERE ticket=? AND kind='build' AND sha IS NOT NULL ORDER BY id LIMIT 1",
                        (t['id'],)).fetchone()
    if first and first['base_sha']:
        return first['base_sha']
    if first:
        git('fetch', '--quiet', 'origin', t['base'], cwd=repo['path'], check=False)
        res = git('rev-parse', f'{first["sha"]}^', cwd=repo['path'], check=False)
        if res.returncode == 0:
            return res.stdout.strip()
    raise db.RunwayError(f'{t["id"]} has no build to take a base commit from')


def run(con, tids, agents=ENGINES, runner=None, log=print):
    runner = runner or LocalRunner()
    signed = [a['kind'] for a in con.execute('SELECT kind FROM agents WHERE signed_in = 1')]
    if not all(e in signed for e in ENGINES):
        raise db.RunwayError('head-to-head needs both Claude Code and Codex signed in. With one engine, everything '
                             'else works as normal: two fresh review sessions on that engine.')
    agents = [a for a in agents if a]
    if not agents or any(a not in ENGINES for a in agents):
        raise db.RunwayError('--agents takes claude, codex or both')
    results = []
    for tid in tids:
        t = db.ticket(con, tid)
        if t['state'] != 'done':
            raise db.RunwayError(f'{tid} is {t["state"]}; head-to-head re-runs done tickets')
        repo = db.repo(con, t['repo'])
        base = base_commit(con, t, repo)
        cfg = runner.config(repo)
        check = check_command(repo, cfg)
        verifies = verify_commands(t)
        jobs = []
        for agent in agents:
            cur = con.execute('INSERT INTO bench(ticket, agent, base_sha, started_at) VALUES (?, ?, ?, ?)',
                              (tid, agent, base, db.now()))
            bid = cur.lastrowid
            rd = db.home() / 'bench' / tid / f'{bid}-{agent}'
            rd.mkdir(parents=True, exist_ok=True)
            wt = runner.worktree(repo, tid, f'bench-{bid}-{agent}', base)          # detached: nothing to push
            fake = dict(t)
            fake['note'] = None
            prompt = worker.build_prompt(fake, repo['name'], base[:10], check, rd / 'outcome.json',
                                         [check] + verifies)
            (rd / 'prompt.md').write_text(prompt)
            session = worker.new_session_id() if agent == 'claude' else None
            line = worker.command(agent, rd / 'prompt.md', rd, wt, [check] + verifies, session_id=session)
            log(f'{tid}: {agent} building from {base[:7]}')
            proc = subprocess.Popen([shell(), '-lc', line], cwd=wt)
            jobs.append((bid, agent, rd, wt, proc, time.time()))
            con.execute('UPDATE bench SET run_dir=?, worktree=? WHERE id=?', (str(rd), str(wt), bid))
        for bid, agent, rd, wt, proc, started in jobs:
            try:
                proc.wait(timeout=TIMEOUT)
            except subprocess.TimeoutExpired:
                proc.kill()
            minutes = round((time.time() - started) / 60, 1)
            outcome = read_json(rd / 'outcome.json')
            changed = bool(git('status', '--porcelain', cwd=wt, check=False).stdout.strip())
            ok_check, check_out = runner.check(wt, check)
            failed = []
            if outcome.get('status') != 'done':
                failed.append(f'worker said {outcome.get("status") or "nothing"}')
            if not changed:
                failed.append('changed nothing')
            if not ok_check:
                failed.append('check failed')
            for n, cmd in enumerate(verifies, 1):
                ok, _ = runner.check(wt, cmd)
                if not ok:
                    failed.append(f'verify {n} failed: {cmd}')
            tin, tout, cost = worker.usage(agent, read(rd / 'log'))
            result = 'pass' if not failed else 'fail'
            con.execute('UPDATE bench SET ended_at=?, result=?, minutes=?, tokens_in=?, tokens_out=?, cost_usd=?, '
                        'detail=?, check_output=? WHERE id=?',
                        (db.now(), result, minutes, tin, tout, cost, '; '.join(failed) or None, check_out[-1500:], bid))
            runner.remove(repo, wt)                                               # the record stays in rd
            results.append({'ticket': tid, 'agent': agent, 'result': result, 'minutes': minutes,
                            'tokens': (tin or 0) + (tout or 0) or None, 'cost_usd': cost,
                            'why': '; '.join(failed) or None, 'record': str(rd)})
            log(f'{tid}: {agent} {result} in {minutes} min')
    return results


def shell():
    import os
    return os.environ.get('SHELL', '/bin/zsh')


def latest(con):
    """The latest result per ticket and engine, for the Stats tab."""
    rows = con.execute('SELECT b.*, t.title FROM bench b JOIN tickets t ON t.id = b.ticket WHERE b.result IS NOT NULL '
                       'ORDER BY b.id').fetchall()
    keep = {}
    for r in rows:
        keep[(r['ticket'], r['agent'])] = r
    return [{'ticket': r['ticket'], 'title': r['title'], 'agent': r['agent'], 'result': r['result'],
             'minutes': r['minutes'], 'cost_usd': r['cost_usd'],
             'tokens': ((r['tokens_in'] or 0) + (r['tokens_out'] or 0)) or None, 'why': r['detail']}
            for r in sorted(keep.values(), key=lambda r: (r['ticket'], r['agent']))]
