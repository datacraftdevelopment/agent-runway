"""What the person decides: go / no on a needs-you ticket, pause and resume, start and stop, where work runs.

A needs-you question has a kind, and go / no mean different things for each:
  merge     the gate wouldn't merge on its own. Go merges the PR now; No with a note sends it back for a fix pass with
            the note; No alone drops the ticket and leaves the PR open.
  question  the worker stopped to ask. Go answers with the recommended option (plus any note); No needs the note,
            which is the answer. Either way the ticket goes back to Up next with the answer.
  failed    a run failed, or the review failed twice. Go tries again (with the note); No drops it.
"""

import json
import re
import time

from . import db
from .github import GitHub


def answer(con, tid, verdict, note=None, github=None):
    t = db.ticket(con, tid)
    if t['state'] not in ('needs_you', 'taken'):
        raise db.RunwayError(f'{tid} is not waiting for you (it is {t["state"]})')
    q = json.loads(t['question'] or '{}')
    kind = q.get('kind', 'failed')
    note = (note or '').strip() or None
    con.execute('INSERT INTO answers(ticket, answer, note, at) VALUES (?, ?, ?, ?)', (tid, verdict, note, db.now()))
    said = f'{verdict}' + (f' ({note})' if note else '')
    if kind == 'merge':
        if verdict == 'go':
            r = db.repo(con, t['repo'])
            gh = github or GitHub()
            pr = gh.pr(r['path'], t['pr'])
            gh.merge(r['path'], t['pr'], pr['headRefOid'])
            db.update_ticket(con, tid, state='done', stage=None, question=None, merged_at=db.now(), merged_by='you',
                             note=f'You merged it at {time.strftime("%H:%M")}.')
            db.event(con, 'merged', f'{tid} PR #{t["pr"]}, merged by you', repo=t['repo'], ticket=tid)
            return f'{tid}: merged PR #{t["pr"]}'
        if note:
            requeue(con, tid, f'The person sent this back from review: {note}', fix=True)
            db.event(con, 'answer', f'{tid}: sent back for a fix pass ({note})', repo=t['repo'], ticket=tid)
            return f'{tid}: back to Up next for a fix pass'
        # No, with nothing to change: like runway drop, the PR is closed (its branch stays on GitHub).
        r = db.repo(con, t['repo'])
        closed = False
        if t['pr']:
            try:
                (github or GitHub()).close(r['path'], t['pr'], 'Not merged: the person said no in Runway.')
                closed = True
            except Exception:
                pass
        db.update_ticket(con, tid, state='dropped', stage='dropped', question=None,
                         note=f'You said no; PR #{t["pr"]} ' + ('closed.' if closed else 'could not be closed.'))
        db.event(con, 'answer', f'{tid}: dropped by you; PR #{t["pr"]} ' + ('closed' if closed else 'left open'),
                 repo=t['repo'], ticket=tid)
        return f'{tid}: dropped, PR #{t["pr"]} ' + ('closed' if closed else 'left open (closing it failed)')
    if kind == 'question':
        if verdict == 'no' and not note:
            raise db.RunwayError('answering differently needs the answer: --note "..."')
        text = q.get('text', '')
        reply = (f'Use what you recommended.' + (f' Also: {note}' if note else '')) if verdict == 'go' else note
        requeue(con, tid, f'You asked: {text}\nThe person answered: {reply}')
        db.event(con, 'answer', f'{tid}: answered ({said})', repo=t['repo'], ticket=tid)
        return f'{tid}: answered, back to Up next'
    if kind == 'taken':
        from . import take
        if verdict == 'go':
            head = take.give(con, tid)
            return f'{tid}: given back at {head[:7]}'
        return take.drop(con, tid, note, github=github)
    # failed (and anything unknown)
    if verdict == 'go':
        requeue(con, tid, note and f'The person says, retrying: {note}')
        db.event(con, 'answer', f'{tid}: try again ({said})', repo=t['repo'], ticket=tid)
        return f'{tid}: back to Up next'
    db.update_ticket(con, tid, state='dropped', stage='dropped', question=None, note='You dropped it.')
    db.event(con, 'answer', f'{tid}: dropped by you', repo=t['repo'], ticket=tid)
    return f'{tid}: dropped'


def requeue(con, tid, note=None, fix=False):
    fields = {'state': 'queued', 'stage': None, 'question': None, 'note': note}
    if not fix:
        fields['fix_passes'] = 0
    db.update_ticket(con, tid, **fields)


DURATION = re.compile(r'^(\d+)\s*([mhd])$')


def until_from(spec):
    """'1h', '30m', '2d' -> epoch seconds; None -> until resumed (stored as far in the future)."""
    if not spec:
        return db.now() + 10 * 365 * 86400
    m = DURATION.match(spec.strip())
    if not m:
        raise db.RunwayError(f'--for takes 30m, 1h or 2d, not {spec!r}')
    return db.now() + int(m.group(1)) * {'m': 60, 'h': 3600, 'd': 86400}[m.group(2)]


def pause(con, target=None, for_=None):
    until = until_from(for_)
    what = target_kind(con, target)
    if what == 'all':
        db.set_meta(con, 'paused_until', until)
    else:
        con.execute(f'UPDATE {what} SET paused_until=? WHERE name=?', (until, target))
    db.event(con, 'setup', f'paused {target or "everything"}' + (f' for {for_}' if for_ else ''),
             repo=target if what == 'repos' else None)
    return f'paused {target or "everything"}' + (f' for {for_}' if for_ else ' until you resume')


def resume(con, target=None):
    what = target_kind(con, target)
    if what == 'all':
        db.set_meta(con, 'paused_until', None)
    else:
        con.execute(f'UPDATE {what} SET paused_until=NULL WHERE name=?', (target,))
    db.event(con, 'setup', f'resumed {target or "everything"}', repo=target if what == 'repos' else None)
    return f'resumed {target or "everything"}'


def target_kind(con, target):
    if not target:
        return 'all'
    if con.execute('SELECT 1 FROM repos WHERE name=?', (target,)).fetchone():
        return 'repos'
    if con.execute('SELECT 1 FROM runners WHERE name=?', (target,)).fetchone():
        return 'runners'
    raise db.RunwayError(f'{target!r} is neither a repo nor a runner')


def start_stop(con, repo, on):
    db.repo(con, repo)
    con.execute('UPDATE repos SET active=? WHERE name=?', (int(on), repo))
    db.event(con, 'setup', f'{"started" if on else "stopped"} {repo}', repo=repo)
    return f'{repo}: {"started" if on else "stopped (running tickets finish; nothing new starts)"}'


def runs_on(con, target, where):
    """A repo: any | main. A ticket: any | <runner> (pins it)."""
    if con.execute('SELECT 1 FROM repos WHERE name=?', (target,)).fetchone():
        if where not in ('any', 'main'):
            raise db.RunwayError('a repo runs on any or main')
        con.execute('UPDATE repos SET runs_on=? WHERE name=?', (where, target))
        return f'{target} runs on {"any runner" if where == "any" else "its main computer only"}'
    t = db.ticket(con, target)
    if where == 'any':
        db.update_ticket(con, t['id'], runs_on=None, pinned=0)
        return f'{t["id"]} runs on any free runner'
    if not con.execute('SELECT 1 FROM runners WHERE name=?', (where,)).fetchone():
        raise db.RunwayError(f'no runner called {where!r}')
    db.update_ticket(con, t['id'], runs_on=where, pinned=1)
    return f'{t["id"]} is pinned to {where}'
