"""How long a ticket took, and how long it's been at what it's doing: from its runs and stops, nothing estimated.

For the board's timers the app gets timestamps (it ticks them itself) and, for a finished ticket, a breakdown:
build (with its check and push), fix passes (builds after the first), reviews (both at once count once), waiting
for the person, and waiting in the queue (the rest).
"""

from . import db


def union(spans):
    """Total seconds covered by (start, end) spans, overlaps counted once."""
    total, cur = 0.0, None
    for s, e in sorted(spans):
        if cur and s <= cur[1]:
            cur[1] = max(cur[1], e)
        else:
            if cur:
                total += cur[1] - cur[0]
            cur = [s, e]
    if cur:
        total += cur[1] - cur[0]
    return total


def ticket(con, t, live=None):
    """The ticket's times: when it started and finished, its current stage and since when, since when it waits (in
    Up next or for the person), and seconds spent on each part."""
    now = db.now()
    runs = con.execute('SELECT * FROM runs WHERE ticket=? ORDER BY started_at', (t['id'],)).fetchall()
    started = runs[0]['started_at'] if runs else None
    finished = None
    if t['state'] == 'done':
        finished = t['merged_at'] or t['updated_at']
    elif t['state'] == 'dropped':
        finished = t['updated_at']
    end = finished or now
    span = lambda r: (r['started_at'], r['ended_at'] or now)
    builds = [r for r in runs if r['kind'] == 'build']
    first = builds[:1]
    parts = {
        'build': union([span(r) for r in first]),
        'fix': union([span(r) for r in builds[1:]]),
        'review': union([span(r) for r in runs if r['kind'] == 'review']),
    }
    # Waiting for the person: from each stop to the next run that started after it (or now / the end).
    stops = [s['at'] for s in con.execute('SELECT at FROM stops WHERE ticket=? ORDER BY at', (t['id'],))]
    waits = []
    for at in stops:
        nxt = next((r['started_at'] for r in runs if r['started_at'] > at), None)
        waits.append((at, nxt or end))
    parts['waiting_for_you'] = union(waits)
    worked = union([span(r) for r in runs] + waits)
    parts['queued'] = max(0.0, (end - t['filed_at']) - worked) if t['filed_at'] else 0.0

    stage, stage_at, waiting_since = None, None, None
    if live:
        stage = live['stage'] or live['kind']
        stage_at = (live['stage_at'] if 'stage_at' in live.keys() and live['stage_at'] else None) or live['started_at']
    if t['state'] == 'queued':
        # Waiting since it was filed, or since its last blocker finished, or since its last run ended.
        unblocked = [con.execute("SELECT updated_at FROM tickets WHERE id=?", (b,)).fetchone()
                     for b in db.blockers(con, t['id'])]
        marks = [t['filed_at']] + [u['updated_at'] for u in unblocked if u] + [r['ended_at'] for r in runs if r['ended_at']]
        waiting_since = max(m for m in marks if m)
    elif t['state'] in ('needs_you', 'taken'):
        waiting_since = stops[-1] if stops else t['updated_at']
    return {
        'filed_at': t['filed_at'], 'started_at': started, 'finished_at': finished,
        'stage': stage, 'stage_started_at': stage_at, 'waiting_since': waiting_since,
        # A ticket done by hand has no runs: its time is filing to done.
        'total_seconds': round(end - started) if started else (round(end - t['filed_at']) if finished else None),
        'parts': {k: round(v) for k, v in parts.items()},
        'runs': [{'kind': r['kind'], 'role': r['role'], 'agent': r['agent'], 'started_at': r['started_at'],
                  'ended_at': r['ended_at'], 'seconds': round((r['ended_at'] or now) - r['started_at'])} for r in runs],
    }


def words(seconds):
    """'45 s', '12 min', '1 h 5 min', '2 d 3 h'."""
    if seconds is None:
        return '-'
    s = int(seconds)
    if s < 60:
        return f'{s} s'
    m = s // 60
    if m < 60:
        return f'{m} min'
    h, m = divmod(m, 60)
    if h < 24:
        return f'{h} h {m} min' if m else f'{h} h'
    d, h = divmod(h, 24)
    return f'{d} d {h} h' if h else f'{d} d'
