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
