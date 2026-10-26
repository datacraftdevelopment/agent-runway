"""Take back and give back (Joe, 2026-10-25).

Take back stops a ticket's worker, keeps its branch and worktree, marks it taken back (so it never counts as
hands-off) and prints a prompt the person pastes into any Claude Code or Codex session. Nothing is relaunched or
resumed: every run keeps its own record in ~/.runway/runs/<ticket>/<n>/ (outcome.json, transcript.jsonl, reviews/),
and the prompt points the new session at it. Give back pushes the person's commits and queues the ticket again from
that branch; its reviews then run on the person's commit.
"""

import json
from pathlib import Path

from . import db, worker
from .runner import LocalRunner, git

OPEN_STATES = ('queued', 'building', 'checking', 'reviewing', 'merging', 'needs_you', 'taken')


def runs(con, tid):
    return con.execute('SELECT * FROM runs WHERE ticket=? ORDER BY id', (tid,)).fetchall()


def short_home(path):
    home = str(Path.home())
    return '~' + str(path)[len(home):] if path and str(path).startswith(home) else str(path)


def verdict_line(text):
    return text or 'not yet'


def show(con, tid):
    """The ticket, its Acceptance lines and every run, with where each one keeps its record."""
    t = db.ticket(con, tid)
    lines = [f'{t["id"]} in {t["repo"]}: {t["title"]}',
             f'state: {t["state"]}   risk: {t["risk"]}   agent: {t["agent"]}   branch: {t["branch"] or "rw/" + tid}'
             + (f'   PR #{t["pr"]}' if t['pr'] else '') + ('   (taken back)' if t['state'] == 'taken' else ''),
             '', 'Acceptance:']
    lines += [f'  - {a}' for a in json.loads(t['acceptance'] or '[]')]
    lines += ['', f'Code review: {verdict_line(t["review"])}',
              f'Function review: {verdict_line(t["function_review"])}']
    if t['body']:
        lines += ['', 'The ticket:', t['body']]
    lines += ['', 'Runs:']
    for n, r in enumerate(runs(con, tid), 1):
        what = r['kind'] if r['kind'] == 'build' else f'{r["role"] or "code"} review'
        rd = db.run_dir(con, r)
        lines.append(f'  {n}. {what} by {r["agent"]}: {r["outcome"] or "running"}, stopped at {r["stage"] or "?"}'
                     + (f', commit {r["sha"][:7]}' if r['sha'] else ''))
        lines.append(f'     record: {short_home(rd)}/  (' + ', '.join(
            name for name in ('outcome.json', 'review.json', 'transcript.jsonl', 'reviews', 'log')
            if (rd / name).exists()) + ')')
        lines.append(f'     session: {r["session_id"] or "none"}   worktree: {short_home(r["dir"]) if r["dir"] else "none"}'
                     + (f'   branch: {r["branch"]}' if r['branch'] else ''))
    return '\n'.join(lines)


def last_build(con, tid):
    return con.execute("SELECT * FROM runs WHERE ticket=? AND kind='build' ORDER BY id DESC LIMIT 1", (tid,)).fetchone()


def prompt(con, tid):
    """What the person pastes into a new Claude Code or Codex session to take over the ticket: the take-back skill
    first, then a compact fallback for a session without the plugin."""
    t = db.ticket(con, tid)
    branch = t['branch'] or f'rw/{tid}'
    q = json.loads(t['question'] or '{}')
    failed = (f'code review: {verdict_line(t["review"])}; function review: {verdict_line(t["function_review"])}')
    if q.get('text') and q.get('kind') in ('failed', 'question'):
        failed += f'. Runway said: {q["text"][:400]}'
    last = con.execute('SELECT * FROM runs WHERE ticket=? ORDER BY id DESC LIMIT 1', (tid,)).fetchone()
    if last:
        engine = {'claude': 'Claude Code', 'codex': 'Codex'}.get(last['agent'], last['agent'])
        record = short_home(db.run_dir(con, last))
        last_line = (f'Last run: {engine}, session {last["session_id"] or "none"}, stopped at '
                     f'{last["stage"] or last["kind"]}. Its transcript and outcome are in {record}/ '
                     f'(transcript.jsonl, outcome.json, reviews/). Read them first to see what it tried.')
    else:
        last_line = 'It has not run yet.'
    frees = [r['ticket'] for r in con.execute(
        "SELECT b.ticket FROM blockers b JOIN tickets x ON x.id = b.ticket WHERE b.blocked_by=? "
        "AND x.state NOT IN ('done', 'dropped')", (tid,))]
    if frees:
        last_line += (f' It blocks {", ".join(frees)}: finishing it (runway give {tid} or runway done {tid}) '
                      'lets Runway start them.')
    return (f'Use the runway take-back skill on ticket {tid} in {t["repo"]}.\n'
            f'\n'
            f'Without the plugin: {tid} is "{t["title"]}", on branch {branch}. Run runway take {tid} (prints the '
            f'worktree), then runway show {tid}. What failed: {failed}. {last_line} Fix it in the worktree, run the '
            f'check, commit, then end it with exactly one of: runway give {tid} (Runway reviews it again), '
            f'runway done {tid} --note "..." (only on the person\'s go: merges it), or '
            f'runway drop {tid} --reason "..." (closes the PR). Never leave it taken back.')


def discuss_prompt(con, tid):
    """What the person pastes to talk a ticket over in Claude Code or Codex, without taking it back: the runway skill
    first, then a short summary for a session without the plugin."""
    t = db.ticket(con, tid)
    pr = f'PR #{t["pr"]}' if t['pr'] else 'no PR yet'
    last = con.execute('SELECT * FROM runs WHERE ticket=? ORDER BY id DESC LIMIT 1', (tid,)).fetchone()
    record = (f'Its last run ({last["kind"]}, {last["outcome"] or "still going"}) keeps its record in '
              f'{short_home(db.run_dir(con, last))}/.' if last else 'It has not run yet.')
    return (f'Use the runway skill to look at ticket {tid} in {t["repo"]} with me. Don\'t take it back or change '
            f'anything unless I ask.\n'
            f'\n'
            f'Without the plugin: {tid} is "{t["title"]}", {t["state"].replace("_", " ")}, on branch '
            f'{t["branch"] or "rw/" + tid}, {pr}. Code review: {verdict_line(t["review"])}; function review: '
            f'{verdict_line(t["function_review"])}. {record} runway show {tid} prints the rest.')


def take(con, tid, runner=None):
    """Stop the worker, keep the branch and worktree, mark it taken back. Running it twice changes nothing more."""
    runner = runner or LocalRunner()
    t = db.ticket(con, tid)
    if t['state'] not in OPEN_STATES:
        raise db.RunwayError(f'{tid} is {t["state"]}; only an open ticket can be taken back')
    repo = db.repo(con, t['repo'])
    branch = t['branch'] or f'rw/{tid}'
    if t['state'] == 'taken' and t['take_dir'] and Path(t['take_dir']).exists():
        return t['take_dir'], branch
    for r in con.execute('SELECT * FROM runs WHERE ticket=? AND ended_at IS NULL', (tid,)).fetchall():
        runner.stop(r['tmux'])
        con.execute("UPDATE runs SET ended_at=?, outcome='taken' WHERE id=?", (db.now(), r['id']))
    wt = worktree_for(con, t, repo, branch, runner)
    con.execute('INSERT INTO stops(ticket, repo, at, reason, detail) VALUES (?, ?, ?, ?, ?)',
                (tid, t['repo'], db.now(), 'taken_back', 'taken back by the person'))
    db.update_ticket(con, tid, state='taken', stage=None, branch=branch, take_dir=str(wt), taken=t['taken'] + 1,
                     question={'kind': 'taken', 'reason': 'taken_back',
                               'text': 'You took this back. Finish it in any Claude Code or Codex session, commit, '
                                       f'then give it back: runway give {tid}.',
                               'short': f'{tid} taken back', 'go_label': 'Give back', 'no_label': 'Drop'})
    db.event(con, 'answer', f'{tid} taken back; worktree {short_home(wt)}, branch {branch}', repo=t['repo'], ticket=tid)
    return str(wt), branch


def worktree_for(con, t, repo, branch, runner):
    """The last build's worktree when it is still there on the branch; else a fresh one on the branch (from origin
    when it was pushed, else from the base)."""
    dirs = [r['dir'] for r in con.execute("SELECT dir FROM runs WHERE ticket=? AND kind='build' AND dir IS NOT NULL "
                                          "ORDER BY id DESC", (t['id'],)) if Path(r['dir']).exists()]
    for d in dirs:
        if git('rev-parse', '--abbrev-ref', 'HEAD', cwd=d, check=False).stdout.strip() == branch:
            return Path(d)
    # None of them is on the branch any more; git won't reset a branch another worktree holds, so clear them.
    for d in dirs:
        runner.remove(repo, d)
    ref = f'origin/{branch}'
    git('fetch', '--quiet', 'origin', repo['base'], f'+refs/heads/{branch}:refs/remotes/origin/{branch}',
        cwd=repo['path'], check=False)
    if not runner.has_ref(repo, ref):
        ref = f'origin/{repo["base"]}'
    return runner.worktree(repo, t['id'], 'take', ref, branch=branch)


def give(con, tid, runner=None):
    """Push the person's commits on the branch and queue the ticket again from them."""
    runner = runner or LocalRunner()
    t = db.ticket(con, tid)
    if t['state'] != 'taken':
        raise db.RunwayError(f'{tid} is not taken back (it is {t["state"]})')
    wt, branch = t['take_dir'], t['branch'] or f'rw/{tid}'
    if not wt or not Path(wt).exists():
        raise db.RunwayError(f'the take-back worktree for {tid} is gone; run runway take {tid} again')
    if git('status', '--porcelain', cwd=wt).stdout.strip():
        raise db.RunwayError(f'{short_home(wt)} has uncommitted changes; commit them (or stash them) first')
    head = runner.head(wt)
    runner.push(wt, branch)
    runner.remove(db.repo(con, t['repo']), wt)
    db.update_ticket(con, tid, state='queued', stage=None, question=None, take_dir=None, fix_passes=0,
                     note=f'The person took this ticket over and committed on {branch} (head {head[:7]}). Carry on '
                          'from their commits: check every Acceptance line and finish only what is still missing. If '
                          'nothing is missing, change nothing and report done.')
    db.event(con, 'answer', f'{tid} given back at {head[:7]}; it builds again from that commit', repo=t['repo'],
             ticket=tid)
    return head


def push_mine(con, t, runner):
    """The person's commits in the take-back worktree, pushed to the branch. Refuses uncommitted work."""
    wt = t['take_dir']
    if not wt or not Path(wt).exists():
        return None
    if git('status', '--porcelain', cwd=wt).stdout.strip():
        raise db.RunwayError(f'{short_home(wt)} has uncommitted changes; commit them (or stash them) first')
    runner.push(wt, t['branch'] or f'rw/{t["id"]}')
    return runner.head(wt)


def remove_worktrees(con, t, runner):
    repo = db.repo(con, t['repo'])
    for d in [t['take_dir']] + [r['dir'] for r in con.execute('SELECT dir FROM runs WHERE ticket=? AND dir IS NOT NULL',
                                                              (t['id'],))]:
        if d and Path(d).exists():
            runner.remove(repo, d)


def done(con, tid, note=None, github=None, runner=None):
    """The person's go, from the session that took it over: push their commits, merge the PR if it isn't merged, and
    record it like runway go. Safe to run again."""
    from .github import GitHub
    runner, gh = runner or LocalRunner(), github or GitHub()
    t = db.ticket(con, tid)
    if t['state'] == 'done':
        return f'{tid} is already done'
    if t['state'] not in OPEN_STATES:
        raise db.RunwayError(f'{tid} is {t["state"]}')
    if not t['pr']:
        raise db.RunwayError(f'{tid} has no PR to merge yet: runway give {tid} lets Runway open one, or drop it')
    repo = db.repo(con, t['repo'])
    head = push_mine(con, t, runner)
    pr = gh.pr(repo['path'], t['pr'])
    if pr['state'] != 'MERGED':
        gh.merge(repo['path'], t['pr'], head or pr['headRefOid'])
    con.execute("INSERT INTO answers(ticket, answer, note, at) VALUES (?, 'go', ?, ?)", (tid, note, db.now()))
    remove_worktrees(con, t, runner)
    db.update_ticket(con, tid, state='done', stage=None, question=None, take_dir=None, merged_at=db.now(),
                     merged_by='you', note='You finished it in your own session and merged it.'
                     + (f' Note: {note}' if note else ''))
    db.event(con, 'merged', f'{tid} PR #{t["pr"]}, merged by you after taking it back', repo=t['repo'], ticket=tid)
    return f'{tid}: merged PR #{t["pr"]} and marked done'


def drop(con, tid, reason=None, github=None, runner=None):
    """Close the PR, remove the worktrees, and move the ticket to Done as dropped. Safe to run again."""
    from .github import GitHub
    runner, gh = runner or LocalRunner(), github or GitHub()
    t = db.ticket(con, tid)
    if t['state'] == 'dropped':
        return f'{tid} is already dropped'
    if t['state'] == 'done':
        raise db.RunwayError(f'{tid} is done (merged); there is nothing to drop')
    for r in con.execute('SELECT * FROM runs WHERE ticket=? AND ended_at IS NULL', (tid,)).fetchall():
        runner.stop(r['tmux'])
        con.execute("UPDATE runs SET ended_at=?, outcome='dropped' WHERE id=?", (db.now(), r['id']))
    if t['pr']:
        repo = db.repo(con, t['repo'])
        if gh.pr(repo['path'], t['pr'])['state'] == 'OPEN':
            gh.close(repo['path'], t['pr'], f'Dropped in Runway: {reason}' if reason else 'Dropped in Runway.')
    con.execute("INSERT INTO answers(ticket, answer, note, at) VALUES (?, 'no', ?, ?)", (tid, reason, db.now()))
    remove_worktrees(con, t, runner)
    db.update_ticket(con, tid, state='dropped', stage='dropped', question=None, take_dir=None,
                     note='Dropped by you.' + (f' Reason: {reason}' if reason else ''))
    db.event(con, 'answer', f'{tid}: dropped by you' + (f' ({reason})' if reason else ''), repo=t['repo'], ticket=tid)
    return f'{tid}: dropped' + (f', PR #{t["pr"]} closed' if t['pr'] else '')
