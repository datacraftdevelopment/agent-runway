"""Retros that open a pull request (Joe, 2026-10-25).

When 3 or more tickets in one repo stop for the same reason within 7 days (the threshold is `retro_threshold` in the
repo's runway.json), or when the person runs `runway retro`, Runway files a ticket itself. Its body lists the failing
runs, each with its record, session, both review verdicts and the check output, and its job is to change the file that
caused the trouble: the repo's runway.json, the agent-runway skills, or the worker and review prompts. A retro is
always not low risk and never merges itself; its PR links every run behind it. Runway never edits prompts or config
outside a reviewed PR.
"""

import json

from . import db, tickets

WINDOW_DAYS = 7
DEFAULT_THRESHOLD = 3
# Stops that aren't trouble to fix: the person's own risk call, and the person stepping in.
NOT_TROUBLE = ('not_low_risk', 'taken_back')


def due(con, repo, threshold=DEFAULT_THRESHOLD):
    """Reasons that stopped `threshold` or more different tickets in `repo` in the last 7 days, with no retro filed
    for that reason in that time."""
    since = db.now() - WINDOW_DAYS * 86400
    rows = con.execute('SELECT reason, COUNT(DISTINCT ticket) n FROM stops WHERE repo=? AND at >= ? '
                       'GROUP BY reason HAVING n >= ? ORDER BY n DESC', (repo, since, threshold)).fetchall()
    out = []
    for r in rows:
        if r['reason'] in NOT_TROUBLE:
            continue
        filed = con.execute("SELECT 1 FROM tickets WHERE kind='retro' AND repo=? AND retro_reason=? AND filed_at >= ?",
                            (repo, r['reason'], since)).fetchone()
        if not filed:
            out.append(r['reason'])
    return out


def behind(con, repo, reason):
    """The runs behind a retro: the latest stop of each ticket that stopped for this reason in the last 7 days."""
    since = db.now() - WINDOW_DAYS * 86400
    stops = con.execute('SELECT * FROM stops WHERE repo=? AND reason=? AND at >= ? ORDER BY id', (repo, reason, since))
    latest = {}
    for s in stops:
        latest[s['ticket']] = s
    out = []
    slug = db.repo(con, repo)['slug']
    for tid, s in latest.items():
        t = db.ticket(con, tid)
        run = con.execute('SELECT * FROM runs WHERE id=?', (s['run'],)).fetchone() if s['run'] else None
        record = str(db.run_dir(con, run)) if run else None
        out.append({
            'ticket': tid, 'title': t['title'], 'run': run['id'] if run else None,
            'engine': run['agent'] if run else None, 'session': run['session_id'] if run else None,
            'record': record, 'transcript': f'{record}/transcript.jsonl' if record else None,
            'pr': t['pr'], 'pr_url': f'https://github.com/{slug}/pull/{t["pr"]}' if slug and t['pr'] else None,
            'code_review': t['review'], 'function_review': t['function_review'],
            'detail': (s['detail'] or '')[:1500],
        })
    return out


def body(reason, runs):
    label = reason.replace('_', ' ')
    lines = [f'{len(runs)} tickets stopped for the same reason in the last {WINDOW_DAYS} days: **{label}**.',
             '', 'Find what caused it and change the file that caused it: the repo\'s runway.json (for example its '
             'check_cmd), the agent-runway plugin skills, or the worker and review prompts (runway/worker.py in '
             'agent-runway). If the cause lives in Runway itself rather than this repo, say so in your summary and change '
             'nothing here. Never weaken a test or a check to make the stops go away.', '', '## The failing runs', '']
    for r in runs:
        lines.append(f'### {r["ticket"]}: {r["title"]}')
        if r['record']:
            lines.append(f'- Run record: {r["record"]}/ (outcome.json, transcript.jsonl, reviews/)')
        if r['session']:
            lines.append(f'- Session: {r["engine"]} {r["session"]} (transcript: {r["transcript"]})')
        if r['pr_url']:
            lines.append(f'- PR: {r["pr_url"]}')
        lines.append(f'- Code review: {r["code_review"] or "not run"}')
        lines.append(f'- Function review: {r["function_review"] or "not run"}')
        if r['detail']:
            lines.append('- What Runway saw (review notes or check output):')
            lines.append('')
            lines.extend('    ' + x for x in r['detail'].splitlines()[:30])
        lines.append('')
    return '\n'.join(lines)


def runs_behind_section(retro_runs):
    """The PR's "Runs behind this" section: one line per failure, linked."""
    lines = ['## Runs behind this', '']
    for r in retro_runs:
        link = f'[{r["ticket"]} PR #{r["pr"]}]({r["pr_url"]})' if r.get('pr_url') else r['ticket']
        where = f' · run record `{r["record"]}`' if r.get('record') else ''
        session = f' · {r["engine"]} session `{r["session"]}`' if r.get('session') else ''
        lines.append(f'- {link}: {r["title"]}{where}{session}')
    return '\n'.join(lines)


def file(con, repo, reason, by_hand=False):
    """File one retro ticket for this repo and reason. Returns its id."""
    runs = behind(con, repo, reason)
    if not runs:
        raise db.RunwayError(f'nothing in {repo} stopped for {reason!r} in the last {WINDOW_DAYS} days')
    label = reason.replace('_', ' ')
    tid = tickets.file_batch(con, repo, [{
        'title': f'Retro: {label} stopped {len(runs)} ticket{"s" if len(runs) != 1 else ""} in {WINDOW_DAYS} days',
        'body': body(reason, runs),
        'acceptance': [f'A1: the cause behind the {label} stops is fixed in the file that caused it, or the summary '
                       'says why it lives outside this repo. Verify: the repo\'s check passes',
                       'A2: no test or check is weakened, skipped or removed. Verify: git diff'],
        'risk': 'not-low', 'agent': 'any',
    }], filed_from='Runway (retro, by hand)' if by_hand else 'Runway (retro)')[0]
    db.update_ticket(con, tid, kind='retro', retro_reason=reason, retro_runs=json.dumps(runs))
    db.event(con, 'filed', f'{tid}: retro for "{label}" ({len(runs)} tickets in {WINDOW_DAYS} days)', repo=repo,
             ticket=tid)
    return tid


def check(con, config_for):
    """Each loop tick: file the retros that are due. `config_for(repo)` gives the repo's runway.json."""
    filed = []
    for r in con.execute('SELECT * FROM repos WHERE active = 1 AND archived_at IS NULL').fetchall():
        threshold = int(config_for(r).get('retro_threshold') or DEFAULT_THRESHOLD)
        for reason in due(con, r['name'], threshold):
            filed.append(file(con, r['name'], reason))
    return filed
