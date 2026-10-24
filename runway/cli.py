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

    sub.add_parser('where', help='print the database path').set_defaults(fn=cmd_where)
    return p


def main(argv=None):
    a = parser().parse_args(argv)
    con = db.connect()
    try:
        a.fn(con, a)
    except db.RunwayError as e:
        print(f'runway: {e}', file=sys.stderr)
        return 1
    finally:
        con.close()
    return 0
