"""A chunk's run journal on the controller: what was captured at start, and what happened since.

Orca holds the live run (tasks, dispatches, worker_done). The journal holds what the
merge gate must not take from anything a worker can edit: each ticket's risk and
blockers as they were when the chunk started, every verdict and the commit it was
given on, and which tickets have landed on the chunk branch. One JSON file per chunk,
outside the repo, under $PM_RUNWAY_HOME (default ~/.pm-runway/runs/).
"""

import hashlib
import json
import os
import re
import time
from pathlib import Path
from string import Template

from . import tickets as tk

PLUGIN = Path(__file__).resolve().parent.parent
MAX_BUILDS = 2          # the first build plus one fix pass; then a needs-you card
AGENTS = ['claude', 'codex']   # machines.json "agents" overrides: the order is the order of preference
COOLDOWN = 30 * 60      # how long an agent rests after a usage limit that named no reset time

# What Claude Code, Codex and Orca print when a subscription's limit refuses a turn. Phrases, not
# bare "rate limit" or 429, so a ticket that is about rate limiting does not trip it.
LIMIT_RE = re.compile(r'usage limit (?:reached|exceeded)|limit reached'
                      r'|hit your (?:usage )?limit|usage_limit_reached|usageLimitExceeded|rateLimitExceeded'
                      r'|rate_limit_error|rate limit(?:ed)? (?:reached|exceeded|hit)|out of (?:extra )?usage', re.I)
RESET_RE = re.compile(r'(?:\|(\d{10})\b|resets_?at\W{1,4}(\d{10}))', re.I)

# Event kinds and the fields each must carry.
KINDS = {
    'run': ('run',),
    'build-dispatched': ('ticket', 'dispatch', 'machine', 'agent'),
    'built': ('ticket', 'outcome'),                 # succeeded: also branch + sha
    'review-dispatched': ('ticket', 'dispatch', 'machine', 'agent'),
    'reviewed': ('ticket', 'verdict', 'sha', 'agent'),   # risk optional: a reviewer may raise it
    'merged': ('ticket', 'sha'),
    'needs-you': ('reason',),                       # ticket optional: chunk-level when absent
    'question': ('reason', 'message'),              # a worker asked; runway-ask answers it in Orca
    'answered': ('ticket', 'answer'),               # the operator's: retry or drop
    'chunk-review-dispatched': ('dispatch', 'agent'),
    'chunk-reviewed': ('verdict', 'sha'),
    'pr': ('number',),
    'gated': ('verdict', 'sha'),
    'limited': ('agent', 'until', 'dispatch'),      # a usage limit ended that dispatch; ticket optional
}


class JournalError(Exception):
    pass


def home():
    return Path(os.environ.get('PM_RUNWAY_HOME', Path.home() / '.pm-runway'))


def config():
    """The controller's machines.json: which Macs take work, how many at once, which agents."""
    path = home() / 'machines.json'
    if not path.exists():
        raise JournalError(f'no {path}: copy {PLUGIN}/templates/runway/machines.json there and edit it')
    cfg = json.loads(path.read_text())
    cfg.setdefault('orca', 'orca')
    cfg.setdefault('builder', 'claude')
    cfg.setdefault('max_running', sum(m.get('slots', 1) for m in cfg.get('machines', [])))
    cfg.setdefault('agents', list(AGENTS))
    if cfg['builder'] not in cfg['agents']:
        cfg['agents'].insert(0, cfg['builder'])
    if not cfg.get('machines'):
        raise JournalError(f'{path} lists no machines')
    return cfg


def path_for(repo, chunk):
    return home() / 'runs' / f'{Path(repo).resolve().name}--{chunk}.json'


def start(repo, tickets_dir, base='main'):
    """Capture the chunk at start. Refuses a chunk whose tickets fail the readiness check."""
    folder = Path(repo) / tickets_dir
    items = tk.load_dir(folder)
    bad = tk.check_all(items)
    not_ready = [t['id'] for t in items if t.get('status') != 'ready-for-agent']
    if bad:
        raise JournalError('tickets fail the readiness check:\n' + '\n'.join(
            f'  {tid}: {p}' for tid, ps in bad.items() for p in ps))
    if not_ready:
        raise JournalError('not ready-for-agent yet: ' + ', '.join(not_ready))
    chunk = items[0]['chunk']
    path = path_for(repo, chunk)
    if path.exists():
        raise JournalError(f'{path} exists: this chunk already started (runway status --chunk {chunk})')
    data = {
        'chunk': chunk, 'repo': str(Path(repo).resolve()), 'tickets_dir': str(tickets_dir),
        'base': base, 'branch': f'chunk/{chunk}', 'run': None, 'started_at': _now(),
        'order': [t['id'] for t in items],
        'tickets': {t['id']: {
            'title': t['title'], 'path': str(Path(t['path']).relative_to(Path(repo))),
            'risk': t['risk'], 'risk_reason': t.get('risk_reason', ''),
            'blocked_by': t['blocked_by'], 'touches': t['touches'], 'model': t['model'],
            'sha256': hashlib.sha256(Path(t['path']).read_bytes()).hexdigest(),
        } for t in items},
        'events': [],
    }
    save(path, data)
    return path, data


def load(repo, chunk):
    path = path_for(repo, chunk)
    if not path.exists():
        raise JournalError(f'no journal for chunk {chunk!r} at {path} (runway start first)')
    return path, json.loads(path.read_text())


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    tmp.replace(path)


def record(data, kind, **fields):
    if kind not in KINDS:
        raise JournalError(f'unknown event {kind!r}; one of {", ".join(KINDS)}')
    missing = [f for f in KINDS[kind] if not fields.get(f)]
    if missing:
        raise JournalError(f'{kind} needs {", ".join(missing)}')
    ticket = fields.get('ticket')
    if ticket and ticket not in data['tickets']:
        raise JournalError(f'no ticket {ticket!r} in chunk {data["chunk"]}')
    if kind == 'built' and fields['outcome'] == 'succeeded' and not (fields.get('branch') and fields.get('sha')):
        raise JournalError('a succeeded build needs branch and sha (checked on origin, not taken from prose)')
    if kind in ('reviewed', 'chunk-reviewed') and fields['verdict'] not in ('pass', 'fail'):
        raise JournalError('verdict is pass or fail')
    if fields.get('risk') and fields['risk'] not in tk.RISKS:
        raise JournalError(f'risk is one of {", ".join(tk.RISKS)}')
    if kind == 'reviewed':
        st = states(data)[ticket]
        if fields['agent'] == st.get('built_by'):
            raise JournalError(f'{ticket} was built by {fields["agent"]}; the review must be the other model')
        if fields['sha'] != st.get('sha'):
            raise JournalError(f'review is for {fields["sha"][:10]} but the built head is {str(st.get("sha"))[:10]}')
    if kind == 'run':
        data['run'] = fields['run']
    data['events'].append({'at': _now(), 'kind': kind, **{k: v for k, v in fields.items() if v is not None}})
    return data


def states(data):
    """Fold the events into one state per ticket."""
    out = {tid: {'state': 'queued', 'builds': 0} for tid in data['order']}
    for ev in data['events']:
        st = out.get(ev.get('ticket'))
        if st is None:
            continue
        kind = ev['kind']
        if kind in ('build-dispatched', 'review-dispatched'):
            st['before'] = {k: v for k, v in st.items() if k != 'before'}
        if kind == 'build-dispatched':
            st.update(state='building', builds=st['builds'] + 1, machine=ev['machine'],
                      built_by=ev['agent'], dispatch=ev['dispatch'])
        elif kind == 'built':
            if ev['outcome'] == 'succeeded':
                st.update(state='built', branch=ev['branch'], sha=ev['sha'])
            else:
                st.update(state='build-failed')
        elif kind == 'review-dispatched':
            st.update(state='reviewing', machine=ev['machine'], dispatch=ev['dispatch'])
        elif kind == 'reviewed':
            st.update(state='review-passed' if ev['verdict'] == 'pass' else 'review-failed')
            if ev.get('risk') == 'not-low':
                st['raised'] = True
        elif kind == 'merged':
            st.update(state='merged', merged_sha=ev['sha'])
        elif kind == 'needs-you':
            st.update(state='needs-you', reason=ev['reason'])
        elif kind == 'limited':
            # A usage limit is not the ticket's failure: undo the dispatch, keep the build count.
            if st.get('dispatch') == ev['dispatch'] and st.get('before'):
                before = st.pop('before')
                st.clear()
                st.update(before)
        elif kind == 'answered':
            if ev['answer'] == 'retry':
                st.update(state='queued', builds=0)
            elif ev['answer'] == 'drop':
                st.update(state='dropped')
        if st['state'] in ('build-failed', 'review-failed') and st['builds'] >= MAX_BUILDS:
            st.update(state='needs-you', reason=f'{st["state"]} after {st["builds"]} builds')
    return out


def chunk_risk(data):
    """low only if every ticket was captured low and no reviewer raised it."""
    st = states(data)
    if any(t['risk'] != 'low' for t in data['tickets'].values()) or any(s.get('raised') for s in st.values()):
        return 'not-low'
    return 'low'


def plan(data, cfg):
    """What to start now: reviews first (they unblock), then builds on the frontier, within slots."""
    st = states(data)
    running = [(tid, s['machine']) for tid, s in st.items() if s['state'] in ('building', 'reviewing')]
    free = {m['name']: m.get('slots', 1) for m in cfg['machines']}
    for _, machine in running:
        if machine in free:
            free[machine] -= 1
    budget = cfg['max_running'] - len(running)
    busy_areas = {a for tid, s in st.items() if s['state'] == 'building' for a in data['tickets'][tid]['touches']}
    merged = {tid for tid, s in st.items() if s['state'] in ('merged', 'dropped')}

    wanted = []
    for tid in data['order']:
        s, t = st[tid], data['tickets'][tid]
        if s['state'] == 'built':
            agent = available([a for a in cfg.get('agents', AGENTS) if a != s['built_by']])
            if agent:   # none: the other model is resting, and the review waits for it
                wanted.append(('review', tid, agent))
    for tid in data['order']:
        s, t = st[tid], data['tickets'][tid]
        ready = s['state'] in ('queued', 'build-failed', 'review-failed') and set(t['blocked_by']) <= merged
        if ready and not (set(t['touches']) & busy_areas):
            agent = available(builders(cfg, t))
            if agent:
                wanted.append(('fix' if s['builds'] else 'build', tid, agent))
                busy_areas |= set(t['touches'])

    starts = []
    for kind, tid, agent in wanted:
        if budget <= 0:
            break
        machine = next((m for m in cfg['machines'] if free.get(m['name'], 0) > 0
                        and agent in m.get('agents', cfg.get('agents', AGENTS))), None)
        if machine is None:
            continue
        free[machine['name']] -= 1
        budget -= 1
        starts.append({'kind': kind, 'ticket': tid, 'agent': agent, 'machine': machine['name'],
                       'argv': worker_argv(data, cfg, machine, kind, tid, agent, st[tid])})
    return starts


def fix_note(data, tid):
    last = next((e for e in reversed(data['events']) if e.get('ticket') == tid
                 and e['kind'] in ('reviewed', 'built') and (e.get('notes') or e.get('note'))), None)
    why = (last.get('notes') or last.get('note')) if last else 'no notes were recorded'
    return ('This is the fix pass, the last one before a person looks at it. Your branch '
            f'{ticket_branch(tid)} already holds the earlier attempt, if it got that far. '
            'What went wrong last time:\n\n' + why)


def chunk_review_argv(data, cfg):
    """The whole-chunk review: one fresh worker on the controller, the other model from the usual
    builder if it isn't resting. None when every agent is resting."""
    agent = available([a for a in cfg.get('agents', AGENTS) if a != cfg['builder']] + [cfg['builder']])
    if agent is None:
        return None
    machine = cfg['machines'][0]
    spec = Template((PLUGIN / 'templates' / 'runway' / 'chunk-review-spec.md').read_text()).substitute(
        chunk=data['chunk'], chunk_branch=data['branch'], base=data['base'],
        tickets_dir=data['tickets_dir'], tickets=', '.join(data['order']))
    argv = [cfg['orca'], 'orchestration', 'worker-start', '--spec', spec,
            '--task-title', f'review chunk {data["chunk"]}', '--worktree', 'new-top-level',
            '--name', f'rw-chunk-review-{data["chunk"]}', '--base-branch', data['branch'],
            '--agent', agent, '--json']
    if data.get('run'):
        argv += ['--run', data['run']]
    if machine.get('on'):
        argv += ['--on', machine['on']]
    repo_sel = (machine.get('repos') or {}).get(Path(data['repo']).name)
    if repo_sel:
        argv += ['--repo', repo_sel]
    return argv


def builders(cfg, ticket):
    """Who may build a ticket, in order: its own model if it names one, else the usual builder first."""
    if ticket['model'] != 'any':
        return [ticket['model']]
    return [cfg['builder']] + [a for a in cfg.get('agents', AGENTS) if a != cfg['builder']]


# Usage limits. One file per controller, not per chunk: a subscription's limit is the account's,
# whichever chunk or Mac ran into it.

def limits(now=None):
    """{agent: {'until': epoch seconds, 'why': text}} for every agent still resting."""
    path = home() / 'limits.json'
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    now = time.time() if now is None else now
    return {a: v for a, v in data.items() if v.get('until', 0) > now}


def set_limit(agent, until, why):
    data = limits()
    data[agent] = {'until': until, 'why': why[:200]}
    path = home() / 'limits.json'
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + '\n')


def available(agents, now=None):
    resting = limits(now)
    return next((a for a in agents if a not in resting), None)


def limit_from(text, now=None):
    """The epoch second an agent can work again, if the text says a usage limit stopped it; else None."""
    if not text or not LIMIT_RE.search(text):
        return None
    now = time.time() if now is None else now
    m = RESET_RE.search(text)
    reset = int(m.group(1) or m.group(2)) if m else 0
    return reset if now < reset < now + 8 * 86400 else int(now + COOLDOWN)


def ticket_branch(tid):
    return f'rw/{tid}'


def worker_argv(data, cfg, machine, kind, tid, agent, st):
    t = data['tickets'][tid]
    template = 'review-spec.md' if kind == 'review' else 'worker-spec.md'
    spec = Template((PLUGIN / 'templates' / 'runway' / template).read_text()).substitute(
        ticket=tid, title=t['title'], ticket_path=t['path'], chunk=data['chunk'],
        chunk_branch=data['branch'], ticket_branch=ticket_branch(tid), sha=st.get('sha', ''),
        fix_note=fix_note(data, tid) if kind == 'fix' else 'This is the first build of this ticket.',
        body=(Path(data['repo']) / t['path']).read_text())
    base = ticket_branch(tid) if kind == 'review' or (kind == 'fix' and st.get('branch')) else data['branch']
    argv = [cfg['orca'], 'orchestration', 'worker-start', '--spec', spec,
            '--task-title', f'{kind} {tid}: {t["title"]}'[:120],
            '--worktree', 'new-top-level', '--name', f'rw-{kind}-{tid}', '--base-branch', base,
            '--agent', agent, '--json']
    if data.get('run'):
        argv += ['--run', data['run']]
    if machine.get('on'):
        argv += ['--on', machine['on']]
    repo_sel = (machine.get('repos') or {}).get(Path(data['repo']).name)
    if repo_sel:
        argv += ['--repo', repo_sel]
    return argv


def _now():
    return time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
