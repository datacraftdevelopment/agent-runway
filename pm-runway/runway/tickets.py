"""Ticket files: parse the front matter and run the readiness check.

A ticket is one Markdown file, docs/maps/<effort>/tickets/NN-slug.md, with a small
YAML-style header the runner reads and Matt Pocock's ticket body the agent reads.
RUNWAY.md is the format's reference; this module is its rules.
"""

import re
from pathlib import Path

RISKS = ('low', 'not-low')
MODELS = ('any', 'claude', 'codex', 'pi')
STATUSES = ('draft', 'ready-for-agent', 'done')
REQUIRED = ('id', 'chunk', 'spec', 'blocked_by', 'touches', 'risk', 'model', 'status')
ID_RE = re.compile(r'^[a-z0-9][a-z0-9-]*$')
ACCEPT_RE = re.compile(r'^- \[[ x]\] A\d+:', re.M)


class TicketError(Exception):
    pass


def _value(raw):
    raw = raw.split(' #', 1)[0].strip()
    if raw.startswith('[') and raw.endswith(']'):
        return [v.strip().strip('"\'') for v in raw[1:-1].split(',') if v.strip()]
    return raw.strip('"\'')


def parse(path):
    """Return the ticket as a dict: header keys, plus title, body and path."""
    path = Path(path)
    text = path.read_text()
    if not text.startswith('---\n'):
        raise TicketError(f'{path.name}: no front matter (the file must start with ---)')
    try:
        header, body = text[4:].split('\n---\n', 1)
    except ValueError:
        raise TicketError(f'{path.name}: front matter is not closed with ---')
    ticket = {}
    for line in header.splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        if ':' not in line:
            raise TicketError(f'{path.name}: header line is not "key: value": {line!r}')
        key, raw = line.split(':', 1)
        ticket[key.strip()] = _value(raw)
    title = re.search(r'^# (.+)$', body, re.M)
    ticket['title'] = title.group(1).strip() if title else ''
    ticket['body'] = body.strip()
    ticket['path'] = str(path)
    for key in ('blocked_by', 'touches'):
        if isinstance(ticket.get(key), str):
            ticket[key] = [] if ticket[key] in ('', 'none') else [ticket[key]]
    return ticket


def section(body, name):
    m = re.search(rf'^## {re.escape(name)}\s*\n(.*?)(?=^## |\Z)', body, re.M | re.S)
    return m.group(1).strip() if m else ''


def problems(ticket, known_ids=None):
    """The readiness rules a single ticket breaks. An empty list means ready."""
    out = []
    for key in REQUIRED:
        if key not in ticket:
            out.append(f'missing header field: {key}')
    tid = ticket.get('id', '')
    if tid and not ID_RE.match(tid):
        out.append(f'id {tid!r}: lowercase letters, digits and dashes only')
    if ticket.get('risk') not in RISKS:
        out.append(f'risk must be one of {", ".join(RISKS)}')
    if ticket.get('risk') == 'low' and not ticket.get('risk_reason'):
        out.append('risk: low needs a one-line risk_reason')
    if ticket.get('model', 'any') not in MODELS:
        out.append(f'model must be one of {", ".join(MODELS)}')
    if ticket.get('status') not in STATUSES:
        out.append(f'status must be one of {", ".join(STATUSES)}')
    if not ticket.get('touches'):
        out.append('touches: name at least one area, so overlapping tickets can be spotted')
    body = ticket.get('body', '')
    if not ticket.get('title'):
        out.append('no "# Title" line')
    if not section(body, 'What to build'):
        out.append('no "## What to build" section')
    accept = section(body, 'Acceptance')
    lines = ACCEPT_RE.findall(accept)
    if not lines:
        out.append('no Acceptance lines ("- [ ] A1: ..." under "## Acceptance")')
    elif accept.count('Verify:') < len(lines):
        out.append('every Acceptance line needs a "Verify:" a stranger can run')
    if not section(body, 'Context'):
        out.append('no "## Context" section pointing at the spec')
    if tid in ticket.get('blocked_by', []):
        out.append('blocked by itself')
    if known_ids is not None:
        for dep in ticket.get('blocked_by', []):
            if dep not in known_ids:
                out.append(f'blocked by unknown ticket {dep!r}')
    return out


def load_dir(directory):
    """Every ticket in a tickets folder, in file order."""
    files = sorted(Path(directory).glob('*.md'))
    if not files:
        raise TicketError(f'no ticket files in {directory}')
    return [parse(f) for f in files]


def check_all(tickets):
    """Problems per ticket id across a whole chunk: per-ticket rules, duplicate ids, cycles."""
    ids = [t.get('id') for t in tickets]
    report = {t.get('id') or t['path']: problems(t, set(ids)) for t in tickets}
    for tid in {i for i in ids if ids.count(i) > 1}:
        report[tid].append('duplicate id')
    chunks = {t.get('chunk') for t in tickets}
    if len(chunks) > 1:
        for t in tickets:
            report[t['id']].append(f'one chunk per folder, found {sorted(c for c in chunks if c)}')
    cycle = find_cycle({t['id']: t.get('blocked_by', []) for t in tickets if t.get('id')})
    if cycle:
        report[cycle[0]].append('blocking cycle: ' + ' -> '.join(cycle))
    return {k: v for k, v in report.items() if v}


def find_cycle(edges):
    state, stack = {}, []

    def visit(n):
        state[n] = 'open'
        stack.append(n)
        for d in edges.get(n, []):
            if state.get(d) == 'open':
                return stack[stack.index(d):] + [d]
            if d in edges and d not in state:
                found = visit(d)
                if found:
                    return found
        state[n] = 'done'
        stack.pop()
        return None

    for n in edges:
        if n not in state:
            found = visit(n)
            if found:
                return found
    return None
