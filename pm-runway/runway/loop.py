"""One tick of the chunk loop, and the loop itself.

A tick reads everything fresh (the journal, Orca's inbox for the chunk's run, git),
does the mechanical steps, writes the journal and returns. No model runs here: every
build, review and fix is a fresh Orca worker with one ticket in its context. Stop the
loop at any point and start it again; the journal is the state.
"""

import json
import re
import shutil
import subprocess
import time
from pathlib import Path

from . import board as bd
from . import gate as gt
from . import journal as jn

VERDICT_RE = re.compile(r'VERDICT:\s*(pass|fail)', re.I)
RISK_RE = re.compile(r'RISK:\s*(low|not-low)', re.I)
SHA_RE = re.compile(r'SHA:\s*([0-9a-f]{7,40})', re.I)


class LoopError(Exception):
    pass


class Orca:
    """The Orca CLI calls a tick makes. Tests swap in a fake."""

    def __init__(self, exe='orca'):
        self.exe = exe

    def call(self, argv):
        out = subprocess.run(argv, capture_output=True, text=True)
        try:
            data = json.loads(out.stdout) if out.stdout.strip() else {}
        except json.JSONDecodeError:
            data = {}
        if out.returncode != 0:
            raise LoopError(f'{" ".join(argv[:3])} failed ({out.returncode}): {(out.stderr or out.stdout).strip()[:400]}')
        return data

    def run_create(self, objective):
        return find(self.call([self.exe, 'orchestration', 'run-create', '--objective', objective, '--json']),
                    'runId', 'run_id', ('run', 'id'))

    def inbox(self, run):
        data = self.call([self.exe, 'orchestration', 'check', '--run', run,
                          '--types', 'worker_done,escalation,question', '--json'])
        res = data.get('result', data)
        return res.get('deliveryId'), res.get('messages', [])

    def ack(self, run, delivery):
        self.call([self.exe, 'orchestration', 'check', '--run', run, '--ack', delivery, '--json'])

    def start(self, argv):
        return find(self.call(argv), 'dispatchId', 'dispatch_id', ('dispatch', 'id'))

    def release(self, dispatch):
        try:
            self.call([self.exe, 'orchestration', 'worker-release', '--dispatch', dispatch, '--json'])
        except LoopError:
            pass  # release is cleanup; a failed one never undoes a recorded result

    def tail(self, dispatch):
        """The worker's latest output as one string, to spot a usage limit it is parked on."""
        try:
            return json.dumps(self.call([self.exe, 'orchestration', 'worker-read', '--dispatch', dispatch,
                                         '--limit', '40', '--json']))
        except LoopError:
            return ''

    def stop(self, dispatch):
        try:
            self.call([self.exe, 'orchestration', 'worker-stop', '--dispatch', dispatch, '--json'])
        except LoopError:
            pass


def find(data, *keys):
    """Pull an id out of a JSON receipt whose exact shape can differ between Orca versions."""
    stack = [data]
    while stack:
        cur = stack.pop()
        if isinstance(cur, dict):
            for k in keys:
                if isinstance(k, tuple):
                    v = cur.get(k[0])
                    if isinstance(v, dict) and v.get(k[1]):
                        return v[k[1]]
                elif cur.get(k):
                    return cur[k]
            stack.extend(v for v in cur.values() if isinstance(v, (dict, list)))
        elif isinstance(cur, list):
            stack.extend(cur)
    raise LoopError(f'no {keys[0]} in Orca receipt: {json.dumps(data)[:300]}')


class Git:
    """The controller's own clone of the repo. Tests swap in a fake."""

    def __init__(self, repo):
        self.repo = repo

    def git(self, *args, cwd=None, check=True):
        out = subprocess.run(['git', '-C', str(cwd or self.repo), *args], capture_output=True, text=True)
        if check and out.returncode != 0:
            raise LoopError(f'git {" ".join(args[:2])} failed: {(out.stderr or out.stdout).strip()[:400]}')
        return out

    def remote_sha(self, branch):
        out = self.git('ls-remote', 'origin', f'refs/heads/{branch}').stdout.split()
        return out[0] if out else None

    def ensure_branch(self, branch, base):
        if not self.remote_sha(branch):
            self.git('fetch', '--quiet', 'origin', base)
            self.git('push', 'origin', f'origin/{base}:refs/heads/{branch}')

    def merge(self, data, ticket, branch, sha, check_cmd):
        """Merge one reviewed ticket into the chunk branch and push. Returns (ok, merged sha or why not)."""
        wt = jn.home() / 'worktrees' / f'{Path(self.repo).name}--{data["chunk"]}'
        self.git('fetch', '--quiet', 'origin', data['branch'], branch)
        if not wt.exists():
            wt.parent.mkdir(parents=True, exist_ok=True)
            self.git('worktree', 'add', '--detach', str(wt), f'origin/{data["branch"]}')
        self.git('checkout', '--quiet', '--detach', f'origin/{data["branch"]}', cwd=wt)
        if self.git('rev-parse', f'origin/{branch}', cwd=wt).stdout.strip() != sha:
            return False, f'{branch} moved after its review'
        m = self.git('merge', '--no-ff', '-m', f'runway: merge {ticket}', sha, cwd=wt, check=False)
        if m.returncode != 0:
            self.git('merge', '--abort', cwd=wt, check=False)
            return False, 'merge conflict with the chunk branch'
        if check_cmd:
            c = subprocess.run(check_cmd, shell=True, cwd=wt, capture_output=True, text=True)
            if c.returncode != 0:
                return False, 'check failed after merging: ' + (c.stdout + c.stderr).strip()[-300:]
        self.git('push', 'origin', f'HEAD:refs/heads/{data["branch"]}', cwd=wt)
        return True, self.git('rev-parse', 'HEAD', cwd=wt).stdout.strip()

    def open_pr(self, data):
        out = subprocess.run(['gh', 'pr', 'create', '--draft', '--base', data['base'], '--head', data['branch'],
                              '--title', f'Chunk {data["chunk"]}',
                              '--body', f'Chunk `{data["chunk"]}`, opened by pm-runway. Tickets: '
                                        + ', '.join(data['order'])],
                             cwd=self.repo, capture_output=True, text=True)
        if out.returncode != 0:
            raise LoopError('gh pr create failed: ' + (out.stderr or out.stdout).strip())
        return out.stdout.strip().rsplit('/', 1)[-1]


def dispatch_owner(data, dispatch):
    """Which ticket (or the chunk) a dispatch belongs to, and as what."""
    for ev in data['events']:
        if ev.get('dispatch') == dispatch and ev['kind'].endswith('-dispatched'):
            return ev
    return None


def tick(data, cfg, orca, git, gh=None, log=print, repo_cfg=None):
    """Advance the chunk one step. Returns the journal; the caller saves it."""
    if not data.get('run'):
        jn.record(data, 'run', run=orca.run_create(f'pm-runway chunk {data["chunk"]}'))
    git.ensure_branch(data['branch'], data['base'])
    repo_cfg = gt.repo_config(data['repo'], data['base']) if repo_cfg is None else repo_cfg

    # 1. What finished since the last tick.
    delivery, messages = orca.inbox(data['run'])
    for msg in messages:
        handle_message(data, msg, git, orca, log)
    if delivery:
        orca.ack(data['run'], delivery)

    # 1b. A worker whose subscription ran out never reports: it sits on the limit message.
    # Stop it, rest that agent, and put its ticket back for the next agent that isn't resting.
    for ev in running_dispatches(data):
        until = jn.limit_from(orca.tail(ev['dispatch']))
        if until:
            orca.stop(ev['dispatch'])
            hit_limit(data, ev, until, 'a usage limit stopped the worker', log)

    # 2. Land every ticket that passed review.
    for tid, s in jn.states(data).items():
        if s['state'] == 'review-passed':
            ok, out = git.merge(data, tid, s['branch'], s['sha'], repo_cfg.get('check_cmd'))
            if ok:
                jn.record(data, 'merged', ticket=tid, sha=out)
                log(f'merged {tid} into {data["branch"]}')
            else:
                jn.record(data, 'built', ticket=tid, outcome='failed', note=out)
                log(f'{tid}: {out}; it goes back for a fix pass')

    # 3. Start what the slots allow, unless the operator paused new work.
    for start in ([] if paused() else jn.plan(data, cfg)):
        dispatch = orca.start(start['argv'])
        kind = 'review-dispatched' if start['kind'] == 'review' else 'build-dispatched'
        jn.record(data, kind, ticket=start['ticket'], dispatch=dispatch,
                  machine=start['machine'], agent=start['agent'])
        log(f'started {start["kind"]} of {start["ticket"]} on {start["machine"]} ({start["agent"]})')

    # 4. The whole chunk, once every ticket has landed.
    st = jn.states(data)
    if st and all(s['state'] in ('merged', 'dropped') for s in st.values()):
        finish(data, cfg, orca, git, gh, log, repo_cfg)
    return data


def handle_message(data, msg, git, orca, log):
    try:
        payload = json.loads(msg.get('payload') or '{}')
    except json.JSONDecodeError:
        payload = {}
    text = f'{msg.get("subject", "")}\n{msg.get("body", "")}'
    owner = dispatch_owner(data, payload.get('dispatchId'))
    if msg.get('type') in ('question', 'escalation'):
        jn.record(data, 'question', ticket=owner.get('ticket') if owner else None,
                  reason=f'{msg.get("type")} from a worker: {msg.get("subject", "")}', message=msg.get('id'))
        log(f'needs you: {msg.get("subject", "")} (answer with runway-ask)')
        return
    if not owner:
        log(f'ignored a worker_done for a dispatch this chunk did not start: {payload.get("dispatchId")}')
        return
    outcome = payload.get('outcome') or 'failed'
    tid = owner.get('ticket')
    until = jn.limit_from(text) if outcome != 'succeeded' else None
    if until:
        hit_limit(data, owner, until, msg.get('subject', '') or 'usage limit', log)
        orca.release(payload.get('dispatchId'))
        return
    if owner['kind'] == 'build-dispatched':
        branch = jn.ticket_branch(tid)
        sha = git.remote_sha(branch) if outcome == 'succeeded' else None
        if outcome == 'succeeded' and not sha:
            jn.record(data, 'built', ticket=tid, outcome='failed', note=f'reported done but {branch} is not on origin')
        else:
            jn.record(data, 'built', ticket=tid, outcome=outcome, branch=branch if sha else None, sha=sha,
                      note=msg.get('body', '')[:2000])
        log(f'{tid} build {outcome}')
    elif owner['kind'] == 'review-dispatched':
        verdict = VERDICT_RE.search(text)
        risk = RISK_RE.search(text)
        sha = SHA_RE.search(text)
        built_sha = jn.states(data)[tid].get('sha')
        ok = outcome == 'succeeded' and verdict and sha and built_sha and built_sha.startswith(sha.group(1).lower())
        jn.record(data, 'reviewed', ticket=tid, agent=owner['agent'], sha=built_sha or 'unknown',
                  verdict=verdict.group(1).lower() if ok else 'fail',
                  risk=risk.group(1).lower() if risk else None, notes=msg.get('body', '')[:4000])
        log(f'{tid} review: {"pass" if ok and verdict.group(1).lower() == "pass" else "fail"}')
    elif owner['kind'] == 'chunk-review-dispatched':
        verdict = VERDICT_RE.search(text)
        head = git.remote_sha(data['branch'])
        sha = SHA_RE.search(text)
        ok = outcome == 'succeeded' and verdict and sha and head and head.startswith(sha.group(1).lower())
        jn.record(data, 'chunk-reviewed', verdict=verdict.group(1).lower() if ok else 'fail',
                  sha=head or 'unknown', notes=msg.get('body', '')[:4000])
    orca.release(payload.get('dispatchId'))


def running_dispatches(data):
    """The dispatch events whose worker has not reported yet."""
    settled = set()
    for ev in data['events']:
        if ev['kind'] == 'limited':
            settled.add(ev['dispatch'])
    st = jn.states(data)
    out = []
    for ev in data['events']:
        if not ev['kind'].endswith('-dispatched') or ev['dispatch'] in settled:
            continue
        if ev['kind'] == 'chunk-review-dispatched':
            if not any(e['kind'] == 'chunk-reviewed' for e in data['events']):
                out.append(ev)
        elif st[ev['ticket']].get('dispatch') == ev['dispatch'] and st[ev['ticket']]['state'] in ('building', 'reviewing'):
            out.append(ev)
    return out


def hit_limit(data, owner, until, why, log):
    agent = owner['agent']
    jn.set_limit(agent, until, why)
    jn.record(data, 'limited', ticket=owner.get('ticket'), dispatch=owner['dispatch'], agent=agent, until=until,
              reason=why[:200])
    when = time.strftime('%H:%MZ', time.gmtime(until))
    log(f'{agent} hit its usage limit ({owner.get("ticket") or "chunk review"}); it rests until {when}, '
        'new work goes to the other agent')


def finish(data, cfg, orca, git, gh, log, repo_cfg):
    events = {e['kind'] for e in data['events']}
    limited = {e['dispatch'] for e in data['events'] if e['kind'] == 'limited'}
    last = next((e for e in reversed(data['events']) if e['kind'] == 'chunk-review-dispatched'), None)
    if last is None or last['dispatch'] in limited:
        argv = jn.chunk_review_argv(data, cfg)
        if argv is None:
            return  # every agent is resting; the next tick after a reset starts it
        dispatch = orca.start(argv)
        jn.record(data, 'chunk-review-dispatched', dispatch=dispatch, agent=argv[argv.index('--agent') + 1])
        log('every ticket has landed; started the whole-chunk review')
        return
    review = next((e for e in reversed(data['events']) if e['kind'] == 'chunk-reviewed'), None)
    if not review:
        return
    if 'pr' not in events:
        jn.record(data, 'pr', number=git.open_pr(data))
    if any(e['kind'] in ('gated', 'needs-you') and not e.get('ticket') for e in data['events']):
        return
    number = next(e['number'] for e in data['events'] if e['kind'] == 'pr')
    result = gt.gate(data, number, gh=gh, act=True, config=repo_cfg)
    if result['merged']:
        jn.record(data, 'gated', verdict='merged', sha=result['head'])
        log(f'chunk {data["chunk"]} merged to {data["base"]} (low risk, every check passed)')
    else:
        jn.record(data, 'needs-you', reason='chunk PR #%s waits for you: %s' % (number, '; '.join(result['reasons'])))
        log(f'chunk {data["chunk"]} needs you: PR #{number}')


def paused():
    return (jn.home() / 'paused').exists()


def set_paused(on):
    flag = jn.home() / 'paused'
    if on:
        flag.parent.mkdir(parents=True, exist_ok=True)
        flag.write_text(time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()) + '\n')
    elif flag.exists():
        flag.unlink()


def heartbeat(data, state):
    """loop.json: what status screens and a menu-bar item read to say whether the loop is alive."""
    import os
    last = next((e for e in reversed(data['events']) if e['kind'] == 'build-dispatched'), None)
    beat = {'pid': os.getpid(), 'state': state, 'chunk': data['chunk'], 'repo': data['repo'],
            'at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'paused': paused(),
            'last_pickup': {k: last[k] for k in ('ticket', 'machine', 'agent', 'at')} if last else None,
            'resting': {a: time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime(v['until'])) for a, v in jn.limits().items()}}
    (jn.home() / 'loop.json').write_text(json.dumps(beat, indent=2) + '\n')
    bd.write(data, beat)


def screen(data, cfg=None, beat=None):
    """The status screen: one page that says whether the loop runs and what it is doing."""
    st = jn.states(data)
    t = data['tickets']
    lines = []
    if beat:
        state = 'PAUSED (no new work starts)' if beat.get('paused') else beat.get('state', '?').upper()
        lines.append(f'Loop: {state}, last tick {beat.get("at")}')
        lp = beat.get('last_pickup')
        if lp:
            lines.append(f'Last pickup: {lp["ticket"]} on {lp["machine"]} ({lp["agent"]}) at {lp["at"]}')
        for agent, until in (beat.get('resting') or {}).items():
            lines.append(f'Resting: {agent} hit its usage limit; it gets new work again after {until}')
    lines.append(f'Chunk {data["chunk"]} -> {data["branch"]} -> {data["base"]}, risk {jn.chunk_risk(data)}')
    groups = [('Building', ('building',)), ('In review', ('reviewing',)),
              ('Waiting to land', ('review-passed', 'built')), ('Fix pass due', ('build-failed', 'review-failed')),
              ('Merged', ('merged',)), ('Dropped', ('dropped',))]
    for label, states in groups:
        rows = [f'  {tid}  {t[tid]["title"]}' + (f'  [{s["machine"]}]' if s.get('machine') and s['state'] in ('building', 'reviewing') else '')
                for tid, s in st.items() if s['state'] in states]
        if rows:
            lines.append(f'{label}:')
            lines.extend(rows)
    merged = {x for x, s in st.items() if s['state'] in ('merged', 'dropped')}
    nxt = [x for x in data['order'] if st[x]['state'] == 'queued']
    if nxt:
        lines.append('Next up:')
        for x in nxt[:8]:
            waits = [b for b in t[x]['blocked_by'] if b not in merged]
            lines.append(f'  {x}  {t[x]["title"]}' + (f'  (waits on {", ".join(waits)})' if waits else '  (ready)'))
    asks = [e for e in data['events'] if e['kind'] in ('needs-you', 'question')]
    asks += [{'ticket': x, 'reason': s.get('reason', '')} for x, s in st.items() if s['state'] == 'needs-you'
             and not any(e.get('ticket') == x and e['kind'] == 'needs-you' for e in data['events'])]
    if asks:
        lines.append('Waiting on you:')
        for e in asks[-6:]:
            lines.append(f'  {e.get("ticket") or "chunk"}: {e["reason"][:150]}')
    return '\n'.join(lines)


def done(data):
    return any(e['kind'] == 'gated' for e in data['events']) or any(
        e['kind'] == 'needs-you' and not e.get('ticket') for e in data['events'])


def run_forever(repo, chunk, every=60, once=False, live=True, log=print):
    cfg = jn.config()
    orca, git = Orca(cfg['orca']), Git(repo)
    notes = []
    while True:
        path, data = jn.load(repo, chunk)
        notes = notes[-8:]
        try:
            tick(data, cfg, orca, git, log=notes.append)
        except (LoopError, gt.GateError, jn.JournalError) as e:
            notes.append(f'tick stopped: {e}')
        jn.save(path, data)
        finished = done(data)
        heartbeat(data, 'finished' if finished else 'running')
        if live:
            print('\033[2J\033[H', end='')
        log(screen(data, cfg, json.loads((jn.home() / 'loop.json').read_text())))
        if notes:
            log('Recent:\n' + '\n'.join('  ' + n for n in notes[-8:]))
        if once or finished:
            return data
        time.sleep(every)


def have(exe):
    return shutil.which(exe) is not None
