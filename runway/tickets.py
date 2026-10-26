"""Filing tickets: validate a batch and write it in one transaction.

A batch arrives as JSON (what the file-tickets skill sends) or as Markdown files with frontmatter (the same fields; the
form a cloud session pushes to the runway/tickets branch). Inside a batch, `blocked_by` may name another ticket of the
same batch by its `key`, or a ticket already filed by its id.
"""

import json
import re

from . import db

AGENTS = ('any', 'claude', 'codex')
RISKS = {'low': 'low', 'not_low': 'not_low', 'not-low': 'not_low'}


def parse_markdown(text):
    """Frontmatter (`key: value`, `key: [a, b]`) plus a body whose first `# ` line is the title."""
    m = re.match(r'^---\n(.*?)\n---\n?(.*)$', text, re.S)
    if not m:
        raise db.RunwayError('a ticket file needs frontmatter between --- lines')
    fields = {}
    for line in m.group(1).splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        key, _, value = line.partition(':')
        value = value.strip()
        if value.startswith('[') and value.endswith(']'):
            fields[key.strip()] = [v.strip().strip('"\'') for v in value[1:-1].split(',') if v.strip()]
        else:
            fields[key.strip()] = value.strip('"\'') if value not in ('', 'null', '~') else None
    body = m.group(2).strip()
    title = fields.get('title')
    if not title:
        heading = re.search(r'^# (.+)$', body, re.M)
        title = heading.group(1).strip() if heading else None
    fields['title'] = title
    fields['body'] = body
    if 'acceptance' not in fields:
        fields['acceptance'] = re.findall(r'^- \[ \] (.+)$', section(body, 'Acceptance'), re.M)
    if 'model' in fields and 'agent' not in fields:
        fields['agent'] = fields.pop('model')
    return fields


def section(body, name):
    m = re.search(rf'^## {re.escape(name)}\s*\n(.*?)(?=^## |\Z)', body, re.M | re.S)
    return m.group(1) if m else ''


def validate(con, repo, tickets):
    """Check a whole batch before anything is written. Returns the cleaned tickets."""
    if db.repo(con, repo)['archived_at']:
        raise db.RunwayError(f'{repo} is archived; runway repo unarchive {repo} first')
    if not tickets:
        raise db.RunwayError('the batch is empty')
    runners = {r['name'] for r in con.execute('SELECT name FROM runners')}
    # One engine is enough; a ticket can only ask for one this Mac has (as the last setup check found).
    engines = [r['kind'] for r in con.execute('SELECT kind FROM agents WHERE signed_in = 1 ORDER BY kind')]
    if not engines:
        raise db.RunwayError('no engine is signed in: Runway needs Claude Code or Codex (runway doctor)')
    names = {'claude': 'Claude Code', 'codex': 'Codex'}
    keys = [t.get('key') for t in tickets if t.get('key')]
    if len(keys) != len(set(keys)):
        raise db.RunwayError('two tickets in the batch share a key')
    clean = []
    for i, t in enumerate(tickets, 1):
        where = f'ticket {t.get("key") or i}'
        title = (t.get('title') or '').strip()
        if not title:
            raise db.RunwayError(f'{where}: no title')
        risk = RISKS.get((t.get('risk') or 'not_low').strip())
        if not risk:
            raise db.RunwayError(f'{where}: risk is low or not-low, not {t.get("risk")!r}')
        reason = (t.get('risk_reason') or '').strip()
        if risk == 'low' and not reason:
            raise db.RunwayError(f'{where}: risk low needs a one-line risk_reason')
        agent = (t.get('agent') or 'any').strip()
        if agent not in AGENTS:
            raise db.RunwayError(f'{where}: agent is any, claude or codex, not {agent!r}')
        if agent != 'any' and agent not in engines:
            raise db.RunwayError(f'{where}: {names[agent]} is not set up on this Mac; use agent "any" (runs on '
                                 f'{" or ".join(names[e] for e in engines)})')
        runs_on = t.get('runs_on') or None
        if runs_on and runs_on not in runners:
            raise db.RunwayError(f'{where}: no runner called {runs_on!r} (have: {", ".join(sorted(runners))})')
        acceptance = t.get('acceptance') or []
        if isinstance(acceptance, str):
            acceptance = [acceptance]
        if not acceptance:
            raise db.RunwayError(f'{where}: needs at least one Acceptance line')
        hands_on = t.get('hands_on') in (True, 1, 'true', 'yes', '1')
        blocked = t.get('blocked_by') or []
        for b in blocked:
            if b in keys:
                continue
            if not con.execute('SELECT 1 FROM tickets WHERE id=?', (b,)).fetchone():
                raise db.RunwayError(f'{where}: blocked_by {b!r} is neither in this batch nor filed')
        clean.append({'key': t.get('key'), 'title': title, 'body': t.get('body') or '', 'acceptance': acceptance,
                      'touches': t.get('touches') or [], 'risk': risk, 'risk_reason': reason or None,
                      'agent': agent, 'runs_on': runs_on, 'pinned': bool(runs_on), 'blocked_by': blocked,
                      'hands_on': hands_on})
    return clean


def file_batch(con, repo, tickets, filed_from='a terminal'):
    """Validate, then file every ticket of the batch at once. Returns the new ids in order."""
    clean = validate(con, repo, tickets)
    base = db.repo(con, repo)['base']
    con.execute('BEGIN IMMEDIATE')
    try:
        ids = {}
        for t in clean:
            tid = db.next_ticket_id(con)
            if t['key']:
                ids[t['key']] = tid
            t['id'] = tid
            stamp = db.now()
            con.execute('INSERT INTO tickets(id, repo, base, title, body, acceptance, touches, risk, risk_reason, agent, '
                        'runs_on, pinned, state, hands_on, filed_from, filed_at, updated_at) '
                        'VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                        (tid, repo, base, t['title'], t['body'], json.dumps(t['acceptance']), json.dumps(t['touches']),
                         t['risk'], t['risk_reason'], t['agent'], t['runs_on'], int(t['pinned']),
                         'hands_on' if t['hands_on'] else 'queued', int(t['hands_on']), filed_from, stamp, stamp))
        for t in clean:
            for b in t['blocked_by']:
                con.execute('INSERT INTO blockers(ticket, blocked_by) VALUES (?, ?)', (t['id'], ids.get(b, b)))
        listed = ', '.join(t['id'] + (' hands-on' if t['hands_on'] else '') for t in clean)
        db.event(con, 'filed', f'{len(clean)} ticket{"s" if len(clean) != 1 else ""} from {filed_from} ({listed})',
                 repo=repo)
        con.execute('COMMIT')
    except Exception:
        con.execute('ROLLBACK')
        raise
    return [t['id'] for t in clean]
