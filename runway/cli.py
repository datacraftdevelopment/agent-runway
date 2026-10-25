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
    from . import setup
    path = Path(a.path).expanduser().resolve()
    if not (path / '.git').exists():
        raise db.RunwayError(f'{path} is not a git clone')
    slug = git_slug(path)
    if not slug:
        raise db.RunwayError(f'{path} has no GitHub origin; Runway opens and merges pull requests on GitHub')
    name = a.name or path.name
    check = a.check or setup.suggest_check(path)
    con.execute('INSERT OR REPLACE INTO repos(name, path, slug, base, main_computer, runs_on, check_cmd) '
                'VALUES (?, ?, ?, ?, ?, ?, ?)', (name, str(path), slug, a.base, a.main, a.runs_on, check))
    db.event(con, 'setup', f'watching {name} ({slug})', repo=name)
    print(f'watching {name}: {path} (base {a.base}, main computer {a.main}, check: {check or "none"})')


def cmd_repo_suggest(con, a):
    from . import setup
    path = Path(a.path).expanduser().resolve()
    out({'path': str(path), 'name': path.name, 'git': (path / '.git').exists(), 'slug': git_slug(path),
         'check': setup.suggest_check(path)})


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
        data = json.loads(Path(a.batch).read_text() if a.batch else sys.stdin.read())
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
    stamp = lambda m: print(f'{__import__("time").strftime("%H:%M:%S")} {m}', flush=True)
    return loop.run_forever(every=a.every, once=a.once, parent=a.parent_pid, log=stamp)


def cmd_doctor(con, a):
    """Checks this Mac: the tools, and whether Claude Code, Codex and GitHub are signed in. Fills the first-run table."""
    from . import setup
    rep = setup.report(con)
    if a.json:
        out(rep)
        return 0 if rep['ready'] else 1
    def mark(row):
        return 'ok ' if row['ok'] else '-- ' if row['optional'] else 'NO '

    def tail(row):
        if row['ok']:
            return ''
        return '   (optional: one engine is enough)' if row['optional'] else f'   fix: {row["fix"]}'
    for t in rep['tools']:
        print(f'{mark(t)} {t["name"]}{tail(t)}')
    for s in rep['signins']:
        print(f'{mark(s)} {s["label"]} signed in{tail(s)}')
    if not rep['engines']:
        print('NO  an engine: Runway needs Claude Code or Codex (either one), installed and signed in')
    c = rep['command']
    print(f'{"ok " if c["linked"] else "-- "} runway in Terminal' + ('' if c['linked'] else '   fix: runway install-command'))
    sk = rep['skills']
    print(f'{"ok " if sk["installed"] else "-- "} skills: {sk["note"]}')
    return 0 if rep['ready'] else 1


def cmd_install_skills(con, a):
    from . import setup
    agents = [x for x in ('claude', 'codex') if getattr(a, x)] or ['claude', 'codex']
    print(setup.install_skills(agents))


def cmd_repo_which(con, a):
    """The repo Runway knows the given folder (default: here) by, for file-tickets."""
    res = subprocess.run(['git', '-C', a.path, 'rev-parse', '--show-toplevel'], capture_output=True, text=True)
    if res.returncode != 0:
        raise db.RunwayError(f'{a.path} is not inside a git clone')
    top = str(Path(res.stdout.strip()).resolve())
    slug = git_slug(top)
    for r in con.execute('SELECT name, path, slug FROM repos'):
        if str(Path(r['path']).resolve()) == top or (slug and r['slug'] == slug):
            print(r['name'])
            return 0
    raise db.RunwayError(f'{top} is not watched by Runway; add it with: runway repo add {top}')


def cmd_install_command(con, a):
    from . import setup
    print(setup.install_command(a.to))


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
    x.add_argument('--check', help="the repo's test command, used when it has no runway.json (default: a guess)")
    x.set_defaults(fn=cmd_repo_add)
    x = r.add_parser('which', help='the name Runway knows this clone by')
    x.add_argument('path', nargs='?', default='.')
    x.set_defaults(fn=cmd_repo_which)
    x = r.add_parser('suggest-check', help='what Runway would guess for a clone: name, GitHub slug, check command')
    x.add_argument('path')
    x.set_defaults(fn=cmd_repo_suggest)
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
    x.add_argument('--batch', help='the JSON batch as a file instead of on stdin')
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
    x = sub.add_parser('doctor', help="check this Mac's tools and sign-ins, with the fix for each")
    x.add_argument('--json', action='store_true', help='what the first-run screen shows')
    x.set_defaults(fn=cmd_doctor)
    x = sub.add_parser('install-skills', help="add Runway's skills to Claude Code and Codex (their plugin commands)")
    x.add_argument('--claude', action='store_true', help='only Claude Code')
    x.add_argument('--codex', action='store_true', help='only Codex')
    x.set_defaults(fn=cmd_install_skills)
    x = sub.add_parser('install-command', help='link runway into ~/.local/bin so Terminal finds it')
    x.add_argument('--to', help='another folder for the link')
    x.set_defaults(fn=cmd_install_command)

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
