"""runway status --json: the one snapshot the app draws. Same shape as app/Tests/.../sample-status.json."""

import json
import time

from . import db

AGENT_NAMES = {'claude': 'Claude Code', 'codex': 'Codex'}
# Event kinds the app knows how to colour; anything else is shown as 'other'.
EVENT_KINDS = {'filed', 'start', 'review', 'merged', 'needs_you', 'limit', 'failed', 'setup', 'answer'}


def iso(ts):
    return None if ts is None else time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(ts))


def clock(ts):
    return time.strftime('%H:%M', time.localtime(ts))


def live_runs(con):
    return con.execute('SELECT * FROM runs WHERE ended_at IS NULL ORDER BY id').fetchall()


def paused_until(con):
    v = db.meta(con, 'paused_until')
    return float(v) if v and float(v) > db.now() else None


def ticket_json(con, t, run, slugs=None):
    column, stage = db.STATES.get(t['state'], ('up_next', None))
    open_blockers = [b for b in db.blockers(con, t['id'])
                     if con.execute("SELECT 1 FROM tickets WHERE id=? AND state NOT IN ('done', 'dropped')",
                                    (b,)).fetchone()]
    question = json.loads(t['question']) if t['question'] else None
    if question:
        question = {k: question.get(k) for k in ('text', 'short', 'go_label', 'no_label')}
        question['go_label'] = question['go_label'] or 'Go'
        question['no_label'] = question['no_label'] or 'No'
    runs_on = t['runs_on'] or (run['runner'] if run else None)
    if not runs_on and t['state'] in ('needs_you', 'done'):
        last = con.execute('SELECT runner FROM runs WHERE ticket=? ORDER BY id DESC LIMIT 1', (t['id'],)).fetchone()
        runs_on = last['runner'] if last else None
    return {
        'id': t['id'], 'repo': t['repo'], 'title': t['title'], 'column': column, 'stage': stage,
        'agent': t['agent'], 'risk': t['risk'], 'runs_on': runs_on, 'pinned': bool(t['pinned']),
        'pr': pr_label(t), 'review': t['review'],
        'pr_url': f'https://github.com/{slugs[t["repo"]]}/pull/{t["pr"]}' if t['pr'] and (slugs or {}).get(t['repo'])
        else None, 'question': question if column == 'needs_you' else None,
        'filed_from': t['filed_from'], 'filed_at': iso(t['filed_at']), 'waits_on': open_blockers,
        'elapsed': int(db.now() - run['started_at']) if run else None,
        'summary': summary(t, run, open_blockers),
    }


def pr_label(t):
    if not t['pr']:
        return None
    if t['state'] == 'done':
        return f'#{t["pr"]} merged' if t['stage'] != 'dropped' else f'#{t["pr"]}'
    return f'#{t["pr"]}' + (' (draft)' if t['state'] in ('building', 'checking', 'reviewing') else '')


def summary(t, run, open_blockers):
    state = t['state']
    who = AGENT_NAMES.get(run['agent'], run['agent']) if run else None
    if state == 'queued':
        if open_blockers:
            return f'Waits for {", ".join(open_blockers)} to finish first.'
        if t['pinned'] and t['runs_on']:
            return f'Pinned to {t["runs_on"]}. Starts when it has a free slot, even if other runners are free.'
        return 'Starts when a runner has a free slot.' + (f' Next run carries a note: {t["note"]}' if t['note'] else '')
    if state == 'building' and run:
        return f'Building with {who}, {int((db.now() - run["started_at"]) // 60)} min in.'
    if state == 'checking':
        return 'Running the repo\'s check command on the built commit.'
    if state == 'reviewing' and run:
        return f'{who} is reviewing commit {(run["sha"] or "")[:7]}.'
    if state == 'merging':
        return 'Waiting for the PR\'s checks before the gate merges it.'
    if state == 'dropped':
        return 'Dropped.'
    return t['note'] if state == 'done' else None


def repo_json(con, r, tickets, pause):
    mine = [t for t in tickets if t['repo'] == r['name']]
    running = [t for t in mine if t['column'] == 'running']
    need = [t for t in mine if t['column'] == 'needs_you']
    up = [t for t in mine if t['column'] == 'up_next']
    until = max([x for x in (r['paused_until'], pause) if x and x > db.now()], default=None)
    if not r['active']:
        state, line = 'off', 'Stopped'
    elif until:
        state, line = 'paused', f'Paused until {clock(until)}'
    elif running:
        state, line = 'running', 'Running' + (f' · {len(need)} need you' if need else f' · {len(up)} up next')
    elif need:
        state, line = 'needs_you', f'{len(need)} need{"s" if len(need) == 1 else ""} you'
    else:
        state, line = 'idle', f'Idle · {len(up)} up next' if up else 'Idle · nothing queued'
    return {'name': r['name'], 'state': state, 'status_line': line, 'main_computer': r['main_computer'],
            'runs_on': r['runs_on']}


def snapshot(con):
    runs = {r['ticket']: r for r in live_runs(con)}
    slugs = {r['name']: r['slug'] for r in con.execute('SELECT name, slug FROM repos')}
    tickets = [ticket_json(con, t, runs.get(t['id']), slugs)
               for t in con.execute('SELECT * FROM tickets ORDER BY filed_at, CAST(SUBSTR(id, 3) AS INTEGER)')]
    pause = paused_until(con)
    used = {}
    for r in runs.values():
        used[r['runner']] = used.get(r['runner'], 0) + 1
    events = con.execute('SELECT * FROM (SELECT * FROM events ORDER BY id DESC LIMIT 200) ORDER BY id').fetchall()
    return {
        'version': 1,
        'generated_at': iso(db.now()),
        'paused_until': iso(pause),
        'repos': [repo_json(con, r, tickets, pause) for r in con.execute('SELECT * FROM repos ORDER BY name')],
        'runners': [{'name': r['name'], 'kind': r['kind'], 'slots_used': used.get(r['name'], 0),
                     'slots_total': r['slots'], 'state': r['state']}
                    for r in con.execute("SELECT * FROM runners ORDER BY kind != 'this_mac', name")],
        'agents': [{'kind': a['kind'],
                    'resting_until': iso(a['resting_until']) if a['resting_until'] and a['resting_until'] > db.now()
                    else None}
                   for a in con.execute('SELECT * FROM agents ORDER BY kind')],
        'tickets': tickets,
        'activity': [{'at': iso(e['at']), 'kind': e['kind'] if e['kind'] in EVENT_KINDS else 'other',
                      'repo': e['repo'], 'text': e['text']} for e in events],
        'setup': [{'runner': s['runner'], 'reachable': s['reachable'], 'claude': s['claude'], 'codex': s['codex'],
                   'github': s['github']} for s in con.execute('SELECT * FROM setup ORDER BY runner')],
    }
