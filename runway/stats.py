"""runway stats: how hands-off Runway is, from the tickets and runs already in the database.

Hands-off: a merged ticket that needed nothing from the person: the gate merged it, no needs-you question about it was
answered, and it was never taken back. Cycle time is filing to merge. Cost is what the engines reported for every run
of the ticket (Claude Code reports dollars and tokens; Codex reports tokens only); nothing is estimated. "Where it
stopped" counts every time a ticket needed the person, by reason.
"""

import statistics

from . import db

WINDOWS = (7, 30)
REASONS = {
    'not_low_risk': 'not low risk',
    'sensitive_path': 'sensitive path',
    'check': 'checks failed',
    'check_failed_twice': 'check failed twice',
    'code_review_failed_twice': 'code review failed twice',
    'function_review_failed_twice': 'function review failed twice',
    'review': 'no passing review',
    'worker_question': 'worker question',
    'build_failed_twice': 'build failed twice',
    'failed_twice': 'failed twice',
    'taken_back': 'taken back',
}


# An archived repo is out of the all-repos numbers (its own tickets stay in the database).
ARCHIVED_OUT = 'AND repo NOT IN (SELECT name FROM repos WHERE archived_at IS NOT NULL)'


def median(xs):
    xs = [x for x in xs if x is not None]
    return statistics.median(xs) if xs else None


def window(con, days, repo=None):
    since = db.now() - days * 86400
    where, args = ('AND repo = ?', (repo,)) if repo else (ARCHIVED_OUT, ())
    merged = con.execute(f"SELECT * FROM tickets WHERE merged_at IS NOT NULL AND merged_at >= ? {where} "
                         "ORDER BY merged_at", (since, *args)).fetchall()
    answered = {r['ticket'] for r in con.execute('SELECT DISTINCT ticket FROM answers')}
    hands_off = [t for t in merged if t['merged_by'] == 'gate' and t['id'] not in answered and not t['taken']]
    rest = [t for t in merged if t not in hands_off]
    minutes = lambda ts: [(t['merged_at'] - t['filed_at']) / 60 for t in ts]

    # Cost per merged ticket: every run of it (builds and both reviews), per engine.
    per_ticket, per_agent = [], {}
    for t in merged:
        runs = con.execute('SELECT agent, tokens_in, tokens_out, cost_usd FROM runs WHERE ticket=?', (t['id'],)).fetchall()
        usd = [r['cost_usd'] for r in runs if r['cost_usd'] is not None]
        tokens = sum((r['tokens_in'] or 0) + (r['tokens_out'] or 0) for r in runs)
        per_ticket.append({'usd': sum(usd) if usd else None, 'tokens': tokens or None})
        for agent in {r['agent'] for r in runs}:
            mine = [r for r in runs if r['agent'] == agent]
            a = per_agent.setdefault(agent, {'usd': [], 'tokens': []})
            mine_usd = [r['cost_usd'] for r in mine if r['cost_usd'] is not None]
            a['usd'].append(sum(mine_usd) if mine_usd else None)
            a['tokens'].append(sum((r['tokens_in'] or 0) + (r['tokens_out'] or 0) for r in mine) or None)

    stops = con.execute(f"SELECT reason, COUNT(*) n FROM stops WHERE at >= ? {where} GROUP BY reason ORDER BY n DESC",
                        (since, *args)).fetchall()
    return {
        'days': days,
        'merged': len(merged),
        'hands_off': len(hands_off),
        'hands_off_rate': round(len(hands_off) / len(merged), 3) if merged else None,
        'hands_off_tickets': [t['id'] for t in hands_off],
        'other_tickets': [t['id'] for t in rest],
        'cycle_minutes': {'hands_off': rounded(median(minutes(hands_off))), 'rest': rounded(median(minutes(rest)))},
        'cost_per_ticket': {
            'median_usd': rounded(median(p['usd'] for p in per_ticket), 4),
            'median_tokens': whole(median(p['tokens'] for p in per_ticket)),
            'by_agent': [{'agent': a, 'tickets': len(v['tokens']), 'median_usd': rounded(median(v['usd']), 4),
                          'median_tokens': whole(median(v['tokens']))} for a, v in sorted(per_agent.items())],
        },
        'stopped': [{'reason': s['reason'], 'label': REASONS.get(s['reason'], s['reason'].replace('_', ' ')),
                     'count': s['n']} for s in stops],
    }


def whole(x):
    return None if x is None else int(round(x))


def rounded(x, digits=1):
    return None if x is None else round(x, digits)


def waiting(con, repo=None):
    """Tickets waiting for the person right now, with why."""
    import json
    where, args = ('AND repo = ?', (repo,)) if repo else (ARCHIVED_OUT, ())
    out = []
    for t in con.execute(f"SELECT id, repo, title, question, state FROM tickets WHERE state IN ('needs_you', 'taken') "
                         f"{where} ORDER BY filed_at", args):
        q = json.loads(t['question'] or '{}')
        last = con.execute('SELECT reason FROM stops WHERE ticket=? ORDER BY id DESC LIMIT 1', (t['id'],)).fetchone()
        reason = ('taken_back' if t['state'] == 'taken'
                  else q.get('reason') or (last['reason'] if last else None) or q.get('kind') or 'other')
        out.append({'id': t['id'], 'repo': t['repo'], 'title': t['title'], 'reason': reason,
                    'label': REASONS.get(reason, reason.replace('_', ' '))})
    return out


def snapshot(con, repo=None, days=None):
    """Everything the board's strip shows: all repos and each repo, for 7 and 30 days (or just the asked-for ones)."""
    windows = (days,) if days else WINDOWS
    repos = [repo] if repo else [r['name'] for r in con.execute(
        'SELECT name FROM repos WHERE archived_at IS NULL ORDER BY name')]

    def scope(name):
        return {'repo': name, 'windows': [window(con, d, name) for d in windows], 'waiting': waiting(con, name)}
    # Lists, not maps keyed by repo or agent name, so no name is ever rewritten by a client's key decoding.
    from . import bench
    rows = bench.latest(con)
    if repo:
        rows = [r for r in rows if db.ticket(con, r['ticket'])['repo'] == repo]
    else:
        archived = {r['name'] for r in con.execute('SELECT name FROM repos WHERE archived_at IS NOT NULL')}
        rows = [r for r in rows if db.ticket(con, r['ticket'])['repo'] not in archived]
    return {'windows': list(windows), 'all': None if repo else scope(None),
            'by_repo': [scope(name) for name in repos], 'bench': rows}
