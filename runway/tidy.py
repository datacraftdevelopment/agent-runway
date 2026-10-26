"""Clearing things away: archive or remove a repo, clear Done tickets off the board, delete one ticket.

Archive and clear-done hide and keep: nothing is deleted, stats and history still count it, and both undo. Remove and
delete are for good: the rows, the run folders under ~/.runway and Runway's own worktrees go. None of them ever
touches the repo's own folder, its branches, or its pull requests on GitHub. All of them refuse while a ticket is
running, and say which.
"""

import shutil
from pathlib import Path

from . import db
from .runner import LocalRunner

RUNNING_STATES = ('building', 'checking', 'reviewing', 'merging')


def running(con, repo=None, ticket=None):
    """Tickets with a run going or mid-pipeline, for one repo or one ticket."""
    where, args = ('t.repo = ?', (repo,)) if repo else ('t.id = ?', (ticket,))
    rows = con.execute(
        f"SELECT DISTINCT t.id FROM tickets t LEFT JOIN runs r ON r.ticket = t.id AND r.ended_at IS NULL "
        f"WHERE {where} AND (r.id IS NOT NULL OR t.state IN {RUNNING_STATES}) "
        "ORDER BY CAST(SUBSTR(t.id, 3) AS INTEGER)", args).fetchall()
    return [r['id'] for r in rows]


def refuse_running(con, what, repo=None, ticket=None):
    busy = running(con, repo=repo, ticket=ticket)
    if busy:
        raise db.RunwayError(f'{", ".join(busy)} {"is" if len(busy) == 1 else "are"} running; '
                             f'wait for {"it" if len(busy) == 1 else "them"} to finish '
                             f'(or runway pause {repo or db.ticket(con, ticket)["repo"]}) before you {what}')


# ---- archive -------------------------------------------------------------------------------------------------------

def archive(con, name):
    r = db.repo(con, name)
    if r['archived_at']:
        return f'{name} is already archived'
    refuse_running(con, f'archive {name}', repo=name)
    con.execute('UPDATE repos SET archived_at=? WHERE name=?', (db.now(), name))
    n = con.execute('SELECT COUNT(*) FROM tickets WHERE repo=?', (name,)).fetchone()[0]
    db.event(con, 'setup', f'archived {name}', repo=name)
    return f'archived {name}: it and its {n} ticket{"" if n == 1 else "s"} are off the board; nothing was deleted ' \
           f'(runway repo unarchive {name} brings them back)'


def unarchive(con, name):
    r = db.repo(con, name)
    if not r['archived_at']:
        return f'{name} is not archived'
    con.execute('UPDATE repos SET archived_at=NULL WHERE name=?', (name,))
    db.event(con, 'setup', f'unarchived {name}', repo=name)
    return f'{name} is back on the board'


# ---- remove --------------------------------------------------------------------------------------------------------

def remove(con, name, runner=None):
    """The repo row and everything Runway keeps for it. Its clone, branches and PRs are left as they are."""
    runner = runner or LocalRunner()
    r = db.repo(con, name)
    refuse_running(con, f'remove {name}', repo=name)
    ids = [t['id'] for t in con.execute('SELECT id FROM tickets WHERE repo=?', (name,))]
    for tid in ids:
        forget_ticket(con, tid, r, runner)
    under_home(db.home() / 'worktrees' / name)
    con.execute('DELETE FROM stops WHERE repo=?', (name,))
    con.execute('DELETE FROM events WHERE repo=?', (name,))
    con.execute('DELETE FROM repos WHERE name=?', (name,))
    db.event(con, 'setup', f'removed {name} from Runway ({len(ids)} ticket{"" if len(ids) == 1 else "s"})')
    return (f'removed {name}: {len(ids)} ticket{"" if len(ids) == 1 else "s"} and their run history are gone. '
            f'Left as they were: {r["path"]}, its branches, and its pull requests on GitHub.')


# ---- tickets -------------------------------------------------------------------------------------------------------

def parse_age(text):
    """'7d', '12h', '30m' or a bare number of days, in seconds."""
    if text is None:
        return None
    units = {'d': 86400, 'h': 3600, 'm': 60}
    t = text.strip().lower()
    try:
        return float(t[:-1]) * units[t[-1]] if t[-1] in units else float(t) * 86400
    except (ValueError, IndexError):
        raise db.RunwayError(f'--older-than takes something like 7d, 12h or 30m, not {text!r}')


def clear_done(con, repo=None, older_than=None):
    """Done and dropped tickets off the board. They stay in the database, in stats and in the activity log. Returns
    the ids cleared, for undo."""
    if repo:
        db.repo(con, repo)
    age = parse_age(older_than)
    sql = "SELECT id FROM tickets WHERE state IN ('done', 'dropped') AND cleared_at IS NULL"
    args = []
    if repo:
        sql += ' AND repo = ?'
        args.append(repo)
    if age is not None:
        sql += ' AND COALESCE(merged_at, updated_at) <= ?'
        args.append(db.now() - age)
    ids = [r['id'] for r in con.execute(sql + ' ORDER BY CAST(SUBSTR(id, 3) AS INTEGER)', args)]
    if ids:
        con.executemany('UPDATE tickets SET cleared_at=? WHERE id=?', [(db.now(), i) for i in ids])
    return ids


def unclear(con, ids):
    """Undo clear-done for these tickets."""
    for tid in ids:
        db.ticket(con, tid)
    con.executemany('UPDATE tickets SET cleared_at=NULL WHERE id=?', [(i,) for i in ids])
    return ids


def delete(con, tid, github=None, runner=None):
    """One ticket for good: its rows, run folders and Runway's worktrees. Its branch and PR stay; says if the PR is
    still open."""
    t = db.ticket(con, tid)
    refuse_running(con, f'delete {tid}', ticket=tid)
    r = db.repo(con, t['repo'])
    forget_ticket(con, tid, r, runner or LocalRunner())
    db.event(con, 'answer', f'{tid} deleted', repo=t['repo'])
    said = f'deleted {tid} ({t["title"]})'
    if t['pr']:
        state = None
        try:
            from .github import GitHub
            state = (github or GitHub()).pr(r['path'], t['pr']).get('state')
        except Exception:
            pass
        if state == 'OPEN':
            said += f'. PR #{t["pr"]} is still open on GitHub; close it there if you don\'t want it'
        elif state is None:
            said += f'. Couldn\'t check PR #{t["pr"]}; it may still be open on GitHub'
    return said


# ---- pieces --------------------------------------------------------------------------------------------------------

def forget_ticket(con, tid, repo, runner):
    t = db.ticket(con, tid)
    dirs = [t['take_dir']] + [x['dir'] for x in con.execute('SELECT dir FROM runs WHERE ticket=?', (tid,))]
    for d in dirs:
        if d and Path(d).exists() and is_under_home(d):
            runner.remove(repo, d)
        if d:
            under_home(d)
    for x in con.execute('SELECT run_dir, worktree FROM bench WHERE ticket=?', (tid,)).fetchall():
        under_home(x['run_dir'])
        under_home(x['worktree'])
    under_home(db.home() / 'runs' / tid)
    for table, col in (('blockers', 'ticket'), ('blockers', 'blocked_by'), ('runs', 'ticket'), ('answers', 'ticket'),
                       ('stops', 'ticket'), ('bench', 'ticket'), ('events', 'ticket')):
        con.execute(f'DELETE FROM {table} WHERE {col}=?', (tid,))
    con.execute('DELETE FROM tickets WHERE id=?', (tid,))


def is_under_home(path):
    try:
        return Path(path).resolve().is_relative_to(db.home().resolve())
    except (OSError, ValueError):
        return False


def under_home(path):
    """Removes a folder only when it is inside ~/.runway: nothing of the person's is ever deleted."""
    if path and is_under_home(path) and Path(path).resolve() != db.home().resolve():
        shutil.rmtree(path, ignore_errors=True)
