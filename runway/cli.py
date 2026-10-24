"""runway: the command the app, the skills and a terminal all use. Every rule lives here, once."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from . import db


def out(obj):
    print(json.dumps(obj, indent=2, sort_keys=True))


# ---- repos and runners -------------------------------------------------------------------------------------------

def git_slug(path):
    """owner/name from the clone's origin URL, or None."""
    res = subprocess.run(['git', '-C', str(path), 'remote', 'get-url', 'origin'], capture_output=True, text=True)
    url = res.stdout.strip()
    if res.returncode != 0 or 'github.com' not in url:
        return None
    tail = url.split('github.com', 1)[1].lstrip(':/')
    return tail[:-4] if tail.endswith('.git') else tail


def cmd_repo_add(con, a):
    path = Path(a.path).expanduser().resolve()
    if not (path / '.git').exists():
        raise db.RunwayError(f'{path} is not a git clone')
    name = a.name or path.name
    con.execute('INSERT OR REPLACE INTO repos(name, path, slug, base, main_computer, runs_on) VALUES (?, ?, ?, ?, ?, ?)',
                (name, str(path), git_slug(path), a.base, a.main, a.runs_on))
    db.event(con, 'setup', f'watching {name} ({path})', repo=name)
    print(f'watching {name}: {path} (base {a.base}, main computer {a.main})')


def cmd_repo_list(con, a):
    out([dict(r) for r in con.execute('SELECT * FROM repos ORDER BY name')])


def cmd_runner_list(con, a):
    out([dict(r) for r in con.execute('SELECT * FROM runners ORDER BY name')])


def cmd_runner_set(con, a):
    con.execute('UPDATE runners SET slots=? WHERE name=?', (a.slots, a.name))
    print(f'{a.name}: {a.slots} slots')


def cmd_where(con, a):
    print(db.db_path())


# ---- filing ------------------------------------------------------------------------------------------------------

def cmd_file(con, a):
    """runway file < batch.json, or runway file --repo r ticket.md ... (the person's go is the approval)."""
    from . import tickets
    if a.files:
        if not a.repo:
            raise db.RunwayError('--repo is required with ticket files')
        batch = [tickets.parse_markdown(Path(f).read_text()) for f in a.files]
        for f, t in zip(a.files, batch):
            t.setdefault('key', t.get('id') or Path(f).stem)
        repo, filed_from = a.repo, a.filed_from or 'a terminal'
    else:
        data = json.loads(sys.stdin.read())
        repo = a.repo or data.get('repo')
        if not repo:
            raise db.RunwayError('name the repo: --repo, or "repo" in the JSON')
        batch, filed_from = data.get('tickets', []), a.filed_from or data.get('filed_from') or 'a terminal'
    ids = tickets.file_batch(con, repo, batch, filed_from=filed_from)
    print(f'filed {len(ids)} to {repo}: {", ".join(ids)}')


# ---- status ------------------------------------------------------------------------------------------------------

def cmd_status(con, a):
    from . import status
    snap = status.snapshot(con)
    if a.json:
        out(snap)
        return
    for r in snap['repos']:
        print(f'{r["name"]}: {r["status_line"]}')
        for t in [t for t in snap['tickets'] if t['repo'] == r['name'] and t['column'] != 'done']:
            where = f' on {t["runs_on"]}' if t['runs_on'] else ''
            print(f'  {t["id"]:6} {t["column"]:9} {t["stage"] or "":7} {t["title"]}{where}')
    for ag in snap['agents']:
        print(f'{ag["kind"]}: ' + (f'resting until {ag["resting_until"]}' if ag['resting_until'] else 'available'))


# ---- the person's decisions --------------------------------------------------------------------------------------

def cmd_go(con, a):
    from . import actions
    print(actions.answer(con, a.ticket, 'go', a.note))


def cmd_no(con, a):
    from . import actions
    print(actions.answer(con, a.ticket, 'no', a.note))


def cmd_pause(con, a):
    from . import actions
    print(actions.pause(con, a.target, getattr(a, 'for')))


def cmd_resume(con, a):
    from . import actions
    print(actions.resume(con, a.target))


def cmd_start(con, a):
    from . import actions
    print(actions.start_stop(con, a.repo, True))


def cmd_stop(con, a):
    from . import actions
    print(actions.start_stop(con, a.repo, False))


def cmd_runs_on(con, a):
    from . import actions
    print(actions.runs_on(con, a.target, a.where))


def cmd_session(con, a):
    """Where a ticket's last run lives and the line that reopens it (the app's Open session)."""
    db.ticket(con, a.ticket)
    run = con.execute('SELECT * FROM runs WHERE ticket=? ORDER BY id DESC LIMIT 1', (a.ticket,)).fetchone()
    if not run:
        raise db.RunwayError(f'{a.ticket} has not run yet')
    if run['ended_at'] is None and run['tmux']:
        line = f'tmux attach -t {run["tmux"]}'
    elif run['agent'] == 'claude' and run['session_id']:
        line = f'claude --resume {run["session_id"]}'
    elif run['agent'] == 'codex' and run['session_id']:
        line = f'codex resume {run["session_id"]}'
    else:
        line = None
    info = {'ticket': a.ticket, 'run': run['id'], 'kind': run['kind'], 'agent': run['agent'], 'runner': run['runner'],
            'dir': run['dir'], 'live': run['ended_at'] is None, 'command': line}
    out(info) if a.json else print(f'cd {run["dir"]} && {line}' if line else f'{run["dir"]} (no session to resume)')


# ---- the loop and setup checks -----------------------------------------------------------------------------------

def cmd_loop(con, a):
    from . import loop
    con.close()
    return loop.run_forever(every=a.every, once=a.once, parent=a.parent_pid)


def login_shell(cmd):
    """A command as the person's login shell runs it, so PATH matches what they use in Terminal."""
    shell = __import__('os').environ.get('SHELL', '/bin/zsh')
    return subprocess.run([shell, '-lc', cmd], capture_output=True, text=True, timeout=60)


def cmd_doctor(con, a):
    """Checks this Mac: the tools, and whether Claude Code, Codex and GitHub are signed in. Fills the first-run table."""
    def claude_ok():
        res = login_shell('claude auth status')
        try:
            return json.loads(res.stdout).get('loggedIn') is True
        except (json.JSONDecodeError, AttributeError):
            return False
    checks = {
        'claude': claude_ok(),
        'codex': login_shell('codex login status').returncode == 0,
        'github': login_shell('gh auth status').returncode == 0,
    }
    tools = {t: login_shell(f'command -v {t}').returncode == 0 for t in ('git', 'tmux', 'claude', 'codex', 'gh')}
    yes = lambda ok: 'yes' if ok else 'sign_in'
    con.execute('INSERT OR REPLACE INTO setup(runner, reachable, claude, codex, github, at) VALUES (?, ?, ?, ?, ?, ?)',
                ('This Mac', 'yes', yes(checks['claude']), yes(checks['codex']), yes(checks['github']), db.now()))
    for agent in ('claude', 'codex'):
        con.execute('UPDATE agents SET signed_in=? WHERE kind=?', (int(checks[agent]), agent))
    for name, ok in {**tools, **{f'{k} signed in': v for k, v in checks.items()}}.items():
        print(f'{"ok " if ok else "NO "} {name}')
    return 0 if all(tools.values()) and all(checks.values()) else 1


# ---- parser ------------------------------------------------------------------------------------------------------

def parser():
    p = argparse.ArgumentParser(prog='runway', description='Runway: tickets run headless, reviewed, merged by a gate.')
    sub = p.add_subparsers(dest='cmd', required=True)

    r = sub.add_parser('repo', help='repos Runway watches').add_subparsers(dest='sub', required=True)
    x = r.add_parser('add', help='watch a local clone')
    x.add_argument('path')
    x.add_argument('--name')
    x.add_argument('--base', default='main')
    x.add_argument('--main', default='This Mac', help='the runner where this clone lives')
    x.add_argument('--runs-on', default='any', choices=['any', 'main'])
    x.set_defaults(fn=cmd_repo_add)
    r.add_parser('list').set_defaults(fn=cmd_repo_list)

    r = sub.add_parser('runner', help='places tickets run').add_subparsers(dest='sub', required=True)
    r.add_parser('list').set_defaults(fn=cmd_runner_list)
    x = r.add_parser('slots', help='how many tickets a runner takes at once')
    x.add_argument('name')
    x.add_argument('slots', type=int)
    x.set_defaults(fn=cmd_runner_set)

    x = sub.add_parser('file', help='file a batch: JSON on stdin, or Markdown ticket files')
    x.add_argument('files', nargs='*')
    x.add_argument('--repo')
    x.add_argument('--filed-from', help='where the batch came from, e.g. "Claude Code on this Mac"')
    x.set_defaults(fn=cmd_file)

    x = sub.add_parser('status', help='what is up next, running, needing you and done')
    x.add_argument('--json', action='store_true', help='the snapshot the app reads')
    x.set_defaults(fn=cmd_status)

    for name, fn, text in (('go', cmd_go, 'go on a needs-you ticket'), ('no', cmd_no, 'no on a needs-you ticket')):
        x = sub.add_parser(name, help=text)
        x.add_argument('ticket')
        x.add_argument('--note', help='anything the agent should know (the answer, for "no" on a question)')
        x.set_defaults(fn=fn)
    for name, fn in (('pause', cmd_pause), ('resume', cmd_resume)):
        x = sub.add_parser(name, help=f'{name} everything, one repo or one runner')
        x.add_argument('target', nargs='?')
        if name == 'pause':
            x.add_argument('--for', help='30m, 1h, 2d; default: until you resume')
        x.set_defaults(fn=fn)
    for name, fn in (('start', cmd_start), ('stop', cmd_stop)):
        x = sub.add_parser(name, help=f'{name} picking up new tickets for a repo')
        x.add_argument('repo')
        x.set_defaults(fn=fn)
    x = sub.add_parser('runs-on', help='where a repo (any|main) or a ticket (any|<runner>) runs')
    x.add_argument('target')
    x.add_argument('where')
    x.set_defaults(fn=cmd_runs_on)
    x = sub.add_parser('session', help="where a ticket's last run is and how to reopen it")
    x.add_argument('ticket')
    x.add_argument('--json', action='store_true')
    x.set_defaults(fn=cmd_session)

    x = sub.add_parser('loop', help='run the loop (the app starts this; one at a time)')
    x.add_argument('--every', type=int, default=15, help='seconds between ticks')
    x.add_argument('--once', action='store_true', help='one tick, then exit')
    x.add_argument('--parent-pid', type=int, help='stop when this process (the app) goes away')
    x.set_defaults(fn=cmd_loop)
    sub.add_parser('doctor', help="check this Mac's tools and sign-ins").set_defaults(fn=cmd_doctor)

    sub.add_parser('where', help='print the database path').set_defaults(fn=cmd_where)
    return p


def main(argv=None):
    a = parser().parse_args(argv)
    con = db.connect()
    try:
        return a.fn(con, a) or 0
    except db.RunwayError as e:
        print(f'runway: {e}', file=sys.stderr)
        return 1
    finally:
        con.close()
