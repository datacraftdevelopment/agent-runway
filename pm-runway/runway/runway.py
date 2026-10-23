#!/usr/bin/env python3
"""runway: pm-runway's ticket checker, chunk journal and loop. Standard library only.

    runway check <tickets-dir | ticket.md>...      the readiness check
    runway start <tickets-dir> [--base main]       capture a chunk so the loop can run it
    runway loop --chunk <name> [--every 60]        the loop: a status screen that redraws each tick
    runway tick --chunk <name>                     one tick, then exit
    runway status [--chunk <name>]                 the status screen, once
    runway board                                   the board page's file:// URL, for Orca's browser tab
    runway pause | resume                          stop or allow new work starting (running work finishes)
    runway plan --chunk <name>                     what the next tick would start, as JSON (starts nothing)
    runway record --chunk <name> <kind> key=value… write one event by hand (runway-ask uses this)
    runway gate --chunk <name> --pr <n> [--merge]  the merge gate on the chunk PR

Run from the repo's root (or pass --repo). The journal lives in $PM_RUNWAY_HOME
(default ~/.pm-runway); the controller's machines are in its machines.json.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from runway import board as bd  # noqa: E402
from runway import gate as gt  # noqa: E402
from runway import journal as jn  # noqa: E402
from runway import loop as lp  # noqa: E402
from runway import tickets as tk  # noqa: E402


def cmd_check(a):
    items = []
    for target in a.paths:
        p = Path(target)
        items += tk.load_dir(p) if p.is_dir() else [tk.parse(p)]
    bad = tk.check_all(items) if len(items) > 1 else {
        items[0].get('id', a.paths[0]): tk.problems(items[0])}
    bad = {k: v for k, v in bad.items() if v}
    for t in items:
        tid = t.get('id', t['path'])
        mark = 'NOT READY' if tid in bad else 'ready'
        print(f'{mark:9}  {tid}  {t.get("title", "")}')
        for prob in bad.get(tid, []):
            print(f'           - {prob}')
    return 1 if bad else 0


def cmd_start(a):
    path, data = jn.start(a.repo, a.tickets_dir, a.base)
    print(f'chunk {data["chunk"]}: {len(data["order"])} tickets captured, risk {jn.chunk_risk(data)}')
    print(f'journal {path}')
    print(f'next: runway loop --chunk {data["chunk"]}')
    return 0


def cmd_loop(a, once=False):
    try:
        lp.run_forever(a.repo, a.chunk, every=a.every, once=once, live=not once)
    except KeyboardInterrupt:
        _, data = jn.load(a.repo, a.chunk)
        lp.heartbeat(data, 'stopped')
        print('\nloop stopped; running workers carry on in Orca. Start it again any time.')
    return 0


def cmd_status(a):
    beat_path = jn.home() / 'loop.json'
    beat = json.loads(beat_path.read_text()) if beat_path.exists() else None
    chunk = a.chunk or (beat or {}).get('chunk')
    if not chunk:
        print('no loop has run yet, and no --chunk given')
        return 1
    repo = a.repo if a.chunk else (beat or {}).get('repo', a.repo)
    _, data = jn.load(repo, chunk)
    print(lp.screen(data, beat=beat if beat and beat.get('chunk') == chunk else None))
    return 0


def cmd_board(a):
    beat_path = jn.home() / 'loop.json'
    beat = json.loads(beat_path.read_text()) if beat_path.exists() else None
    if not beat:
        print('no loop has run yet; the board appears with its first tick')
        return 1
    _, data = jn.load(beat['repo'], beat['chunk'])
    print(bd.write(data, beat).resolve().as_uri())
    return 0


def cmd_pause(a, on):
    lp.set_paused(on)
    print('paused: no new work starts; running workers finish' if on else 'resumed')
    return 0


def cmd_plan(a):
    _, data = jn.load(a.repo, a.chunk)
    print(json.dumps([{k: v for k, v in s.items() if k != 'argv'} | {'argv': s['argv'][:3] + ['…']}
                      for s in jn.plan(data, jn.config())], indent=2))
    return 0


def cmd_record(a):
    path, data = jn.load(a.repo, a.chunk)
    fields = dict(kv.split('=', 1) for kv in a.fields)
    jn.record(data, a.kind, **fields)
    jn.save(path, data)
    print(f'recorded {a.kind} {fields}')
    return 0


def cmd_gate(a):
    _, data = jn.load(a.repo, a.chunk)
    result = gt.gate(data, a.pr, act=a.merge)
    print(json.dumps(result, indent=2))
    return 0 if result['verdict'] == 'merge' else 2


def main(argv=None):
    ap = argparse.ArgumentParser(prog='runway', description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--repo', default='.', help='the repo (default: the current directory)')
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('check')
    p.add_argument('paths', nargs='+')
    p = sub.add_parser('start')
    p.add_argument('tickets_dir')
    p.add_argument('--base', default='main')
    for name in ('loop', 'tick'):
        p = sub.add_parser(name)
        p.add_argument('--chunk', required=True)
        p.add_argument('--every', type=int, default=60)
    p = sub.add_parser('status')
    p.add_argument('--chunk')
    sub.add_parser('board')
    sub.add_parser('pause')
    sub.add_parser('resume')
    p = sub.add_parser('plan')
    p.add_argument('--chunk', required=True)
    p = sub.add_parser('record')
    p.add_argument('--chunk', required=True)
    p.add_argument('kind')
    p.add_argument('fields', nargs='*', help='key=value')
    p = sub.add_parser('gate')
    p.add_argument('--chunk', required=True)
    p.add_argument('--pr', required=True)
    p.add_argument('--merge', action='store_true', help='merge when the gate says merge')
    a = ap.parse_args(argv)
    try:
        return {
            'check': cmd_check, 'start': cmd_start, 'loop': cmd_loop, 'tick': lambda x: cmd_loop(x, once=True),
            'status': cmd_status, 'board': cmd_board, 'pause': lambda x: cmd_pause(x, True), 'resume': lambda x: cmd_pause(x, False),
            'plan': cmd_plan, 'record': cmd_record, 'gate': cmd_gate,
        }[a.cmd](a)
    except (tk.TicketError, jn.JournalError, gt.GateError, lp.LoopError) as e:
        print(f'runway: {e}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
