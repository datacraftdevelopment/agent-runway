"""runway status --json: the one snapshot the app draws. Same shape as app/Tests/.../sample-status.json."""

import json
import os
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
        'pr': pr_label(t), 'review': t['review'], 'function_review': t['function_review'],
        'taken': t['state'] == 'taken', 'kind': t['kind'], 'hands_on': bool(t['hands_on']),
        'done_locally': bool(t['hands_on']) and t['state'] == 'done',
        'taken_hours': taken_hours(con, t),
        'retro_runs': [{'ticket': r['ticket'], 'title': r['title'], 'pr_url': r.get('pr_url'),
                        'record': r.get('record')} for r in json.loads(t['retro_runs'] or '[]')] or None,
        'pr_url': f'https://github.com/{slugs[t["repo"]]}/pull/{t["pr"]}' if t['pr'] and (slugs or {}).get(t['repo'])
        else None, 'question': question if column == 'needs_you' else None,
        'filed_from': t['filed_from'], 'filed_at': iso(t['filed_at']), 'waits_on': open_blockers,
        # What holds it: each open blocker with where it is (and what holds that one), what it blocks, and why the
        # loop isn't starting it (its touches overlap a running ticket, or its Mac is busy).
        'blocked_by': [blocker_json(con, b) for b in open_blockers],
        'blocks': [r['ticket'] for r in con.execute(
            "SELECT b.ticket FROM blockers b JOIN tickets x ON x.id = b.ticket WHERE b.blocked_by=? "
            "AND x.state NOT IN ('done', 'dropped') ORDER BY CAST(SUBSTR(b.ticket, 3) AS INTEGER)", (t['id'],))],
        'hold': t['hold'] if 'hold' in t.keys() else None,
        'timing': timing_json(con, t, run),
        'elapsed': int(db.now() - run['started_at']) if run else None,
        'summary': summary(t, run, open_blockers),
    }


def timing_json(con, t, run):
    """The ticket's times for the board's timers: ISO timestamps the app ticks itself, and seconds per part."""
    from . import timing
    x = timing.ticket(con, t, run)
    return {'started_at': iso(x['started_at']), 'finished_at': iso(x['finished_at']), 'stage': x['stage'],
            'stage_started_at': iso(x['stage_started_at']), 'waiting_since': iso(x['waiting_since']),
            'total_seconds': x['total_seconds'], 'parts': x['parts'],
            'runs': [{'kind': r['kind'], 'role': r['role'], 'agent': r['agent'], 'seconds': r['seconds']}
                     for r in x['runs']]}


def blocker_json(con, tid):
    b = con.execute('SELECT * FROM tickets WHERE id=?', (tid,)).fetchone()
    if not b:
        return {'id': tid, 'column': None, 'title': None, 'waits_on': []}
    theirs = [x for x in db.blockers(con, tid)
              if con.execute("SELECT 1 FROM tickets WHERE id=? AND state NOT IN ('done', 'dropped')", (x,)).fetchone()]
    return {'id': tid, 'title': b['title'], 'column': db.STATES.get(b['state'], ('up_next', None))[0],
            'waits_on': theirs}


def runner_load(r, used):
    """The runner's last reading as the board shows it: sessions running of its max, memory, load and disk, and
    why it's holding work back if it is."""
    from . import capacity
    reading = json.loads(r['reading']) if 'reading' in r.keys() and r['reading'] else None
    lim = capacity.limits(r)
    return {'sessions_running': used, 'sessions_max': r['slots'], 'hold': r['hold'] if 'hold' in r.keys() else None,
            'summary': capacity.summary(reading, lim),
            'available_mb': reading['available_mb'] if reading else None,
            'memory_level': reading.get('memory_level') if reading else None,
            'load_ratio': round(reading['load1'] / max(reading['ncpu'], 1), 2) if reading else None,
            'cpu_used_pct': round(100 - reading['cpu_idle_pct']) if reading and reading.get('cpu_idle_pct') is not None
            else None,
            'disk_free_gb': reading['disk_free_gb'] if reading else None}


def taken_hours(con, t):
    """How long a taken-back ticket has waited, so the board can nudge after a day."""
    if t['state'] != 'taken':
        return None
    row = con.execute("SELECT at FROM stops WHERE ticket=? AND reason='taken_back' ORDER BY id DESC LIMIT 1",
                      (t['id'],)).fetchone()
    return round((db.now() - row['at']) / 3600, 1) if row else None


def pr_label(t):
    if not t['pr']:
        return None
    if t['state'] == 'done':
        return f'#{t["pr"]} merged' if t['stage'] != 'dropped' else f'#{t["pr"]}'
    return f'#{t["pr"]}' + (' (draft)' if t['state'] in ('building', 'checking', 'reviewing') else '')


def summary(t, run, open_blockers):
    state = t['state']
    who = AGENT_NAMES.get(run['agent'], run['agent']) if run else None
    if state == 'hands_on':
        waits = f' Waits for {", ".join(open_blockers)} first.' if open_blockers else ''
        back = f' {t["note"]}' if t['note'] else ''
        return ('Yours to do: Runway never starts this one. Do it in your own session, then '
                f'runway done {t["id"]}.' + waits + back)
    if state == 'queued':
        if open_blockers:
            return f'Waits for {", ".join(open_blockers)} to finish first.'
        parked = resting_for(t)
        if parked:
            return parked
        if t['pinned'] and t['runs_on']:
            return f'Pinned to {t["runs_on"]}. Starts when it has a free slot, even if other runners are free.'
        return 'Starts when a runner has a free slot.' + (f' Next run carries a note: {t["note"]}' if t['note'] else '')
    if state == 'building' and run:
        return f'Building with {who}, {int((db.now() - run["started_at"]) // 60)} min in.'
    if state == 'checking':
        return 'Running the repo\'s check command on the built commit.'
    if state == 'reviewing' and t['hands_on'] and not run:
        return 'Done by hand and checked by you; the code review and the gate are next.'
    if state == 'reviewing' and run:
        role = run['role'] or 'code'
        return f'{who} is doing the {role} review of commit {(run["sha"] or "")[:7]}.'
    if state == 'reviewing':
        return resting_for(t) or 'Waiting for a free slot for its reviews.'
    if state == 'merging':
        return 'Waiting for the PR\'s checks before the gate merges it.'
    if state == 'dropped':
        return 'Dropped.'
    if state == 'done' and t['merged_by'] == 'you_local':
        return t['note'] or 'Done by hand.'
    return t['note'] if state == 'done' else None


_CON = None


def resting_for(t):
    """'Waits for Claude Code's usage limit to reset at 19:30' when no engine the ticket can use is free."""
    if _CON is None:
        return None
    rows = {a['kind']: a for a in _CON.execute('SELECT * FROM agents WHERE signed_in = 1')}
    wanted = [t['agent']] if t['agent'] != 'any' and t['state'] == 'queued' else list(rows)
    resting = [rows[a] for a in wanted if a in rows and rows[a]['resting_until'] and rows[a]['resting_until'] > db.now()]
    if wanted and len(resting) == len([a for a in wanted if a in rows]) and resting:
        soonest = min(resting, key=lambda a: a['resting_until'])
        return (f'Waits for {AGENT_NAMES[soonest["kind"]]}\'s usage limit to reset at '
                f'{clock(soonest["resting_until"])}.')
    return None


def loop_running(con):
    """Whether the loop that last started is still alive (its pid, from the database)."""
    pid = db.meta(con, 'loop_pid')
    try:
        os.kill(int(pid), 0)
        return True
    except (TypeError, ValueError, ProcessLookupError):
        return False
    except PermissionError:
        return True


def why_idle(con, r, mine, pause, running_loop):
    """When a repo has tickets up next but none running, the one reason nothing starts, and the ticket to look at.
    None while something runs, nothing is queued, or the next tick will start one."""
    up = [t for t in mine if t['column'] == 'up_next']
    if not up or any(t['column'] == 'running' for t in mine):
        return None, None
    n = len(up)
    many = f'{n} ticket{"s" if n != 1 else ""} wait{"s" if n == 1 else ""}'
    if not r['active']:
        return f'Nothing can run: {r["name"]} is stopped', None
    if pause or (r['paused_until'] and r['paused_until'] > db.now()):
        return 'Nothing can run: Runway is paused', None
    if not running_loop:
        return "Nothing can run: Runway's loop isn't running", None
    mine_hands_on = [t for t in up if t.get('hands_on')]
    if len(mine_hands_on) == n:
        return f'Nothing can run: {many} on you, to do by hand', mine_hands_on[0]['id']
    if all(t['waits_on'] or t.get('hands_on') for t in up):
        # Follow each chain to the tickets that hold everything up: not themselves waiting in Up next.
        by_id = {t['id']: t for t in mine}
        roots, seen = [], set()

        def walk(tid):
            if tid in seen:
                return
            seen.add(tid)
            t = by_id.get(tid)
            if t and t['column'] == 'up_next' and t['waits_on']:
                for b in t['waits_on']:
                    walk(b)
            elif tid not in roots:
                roots.append(tid)
        for t in up:
            for b in t['waits_on']:
                walk(b)
        where = {'needs_you': 'which needs you', 'running': 'which is running', 'done': 'which is done'}
        hands = [t['id'] for t in mine_hands_on]
        if hands and all(r in hands for r in roots):
            return f'Nothing can run: {many} on {", ".join(hands[:3])}, yours to do by hand', hands[0]
        root = roots[0] if roots else None
        state = where.get(by_id[root]['column'], '') if root in by_id else 'which is in another repo'
        names = ', '.join(roots[:3])
        return f'Nothing can run: {many} on {names}' + (f', {state}' if len(roots) == 1 else ''), root
    held = [t for t in up if t.get('hold') and ' is busy (' in t['hold']]
    if held and len(held) + sum(1 for t in up if t['waits_on']) == n:
        runner = held[0]['hold'].split('waiting: ', 1)[-1].split(' is busy', 1)[0]
        return f'Nothing can run: {many} for room on {runner}', held[0]['id']
    return None, None


def repo_check(r):
    """The check command that applies and where it's set: runway.json on the base branch wins, else Runway's own."""
    import subprocess
    try:
        res = subprocess.run(['git', '-C', r['path'], 'show', f'origin/{r["base"]}:runway.json'], capture_output=True,
                             text=True, timeout=5)
        cmd = json.loads(res.stdout).get('check_cmd') if res.returncode == 0 and res.stdout.strip() else None
    except (OSError, ValueError, subprocess.TimeoutExpired):
        cmd = None
    if cmd:
        return cmd, 'runway.json'
    if r['check_cmd']:
        return r['check_cmd'], 'runway'
    return None, None


def repo_json(con, r, tickets, pause, running_loop=True):
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
    idle, look = why_idle(con, r, mine, until, running_loop)
    check, source = repo_check(r)
    return {'name': r['name'], 'state': state, 'status_line': line, 'main_computer': r['main_computer'],
            'runs_on': r['runs_on'], 'slug': r['slug'], 'path': r['path'], 'idle_reason': idle, 'idle_ticket': look,
            'check_cmd': check, 'check_from': source}


def repo_prompt(con, name):
    """What the person pastes to talk a repo's work over in Claude Code or Codex: the runway skill first, then what
    is queued, running, waiting and recently done, for a session without the plugin."""
    db.repo(con, name)
    snap = snapshot(con)
    mine = [t for t in snap['tickets'] if t['repo'] == name]
    cols = {'needs_you': 'Needs you', 'running': 'Running', 'up_next': 'Up next', 'done': 'Done lately'}
    lines = []
    for col, label in cols.items():
        ts = [t for t in mine if t['column'] == col][-5:] if col == 'done' else [t for t in mine if t['column'] == col]
        if ts:
            lines.append(f'{label}: ' + '; '.join(f'{t["id"]} {t["title"]}' for t in ts))
    return (f'Use the runway skill to look at the {name} repo with me: what is queued, running and waiting for me, '
            f'and how the last tickets went. Don\'t change anything unless I ask.\n'
            f'\n'
            f'Without the plugin: ' + ('. '.join(lines) if lines else 'nothing on the board') +
            f'. runway status prints the board, runway show <ticket> one ticket.')


def snapshot(con):
    global _CON
    _CON = con
    runs = {r['ticket']: r for r in live_runs(con)}
    slugs = {r['name']: r['slug'] for r in con.execute('SELECT name, slug FROM repos')}
    # Archived repos and their tickets, and cleared Done tickets, are off the board (still in the database).
    tickets = [ticket_json(con, t, runs.get(t['id']), slugs)
               for t in con.execute('SELECT t.* FROM tickets t JOIN repos r ON r.name = t.repo '
                                    'WHERE r.archived_at IS NULL AND t.cleared_at IS NULL '
                                    'ORDER BY t.filed_at, CAST(SUBSTR(t.id, 3) AS INTEGER)')]
    pause = paused_until(con)
    used = {}
    for r in runs.values():
        used[r['runner']] = used.get(r['runner'], 0) + 1
    events = con.execute('SELECT * FROM (SELECT * FROM events ORDER BY id DESC LIMIT 200) ORDER BY id').fetchall()
    return {
        'version': 1,
        'generated_at': iso(db.now()),
        'paused_until': iso(pause),
        'loop_running': (alive := loop_running(con)),
        'repos': [repo_json(con, r, tickets, pause, alive)
                  for r in con.execute('SELECT * FROM repos WHERE archived_at IS NULL ORDER BY name')],
        'archived': [{'name': r['name'], 'tickets': r['n']} for r in con.execute(
            'SELECT r.name, COUNT(t.id) n FROM repos r LEFT JOIN tickets t ON t.repo = r.name '
            'WHERE r.archived_at IS NOT NULL GROUP BY r.name ORDER BY r.name')],
        'runners': [{'name': r['name'], 'kind': r['kind'], 'slots_used': used.get(r['name'], 0),
                     'slots_total': r['slots'], 'state': r['state'],
                     'paused_until': iso(r['paused_until']) if r['paused_until'] and r['paused_until'] > db.now()
                     else None, 'load': runner_load(r, used.get(r['name'], 0))}
                    for r in con.execute("SELECT * FROM runners ORDER BY kind != 'this_mac', name")],
        # Only the engines this Mac has: one is enough, and the board never shows one you don't use.
        'agents': [{'kind': a['kind'],
                    'resting_until': iso(a['resting_until']) if a['resting_until'] and a['resting_until'] > db.now()
                    else None}
                   for a in con.execute('SELECT * FROM agents WHERE signed_in = 1 ORDER BY kind')],
        'tickets': tickets,
        'activity': [{'at': iso(e['at']), 'kind': e['kind'] if e['kind'] in EVENT_KINDS else 'other',
                      'repo': e['repo'], 'text': e['text']} for e in events],
        'setup': [{'runner': s['runner'], 'reachable': s['reachable'], 'claude': s['claude'], 'codex': s['codex'],
                   'github': s['github']} for s in con.execute('SELECT * FROM setup ORDER BY runner')],
    }
