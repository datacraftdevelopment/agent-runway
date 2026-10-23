#!/usr/bin/env python3
"""Stack table for /pm-scaffold: which Claude Code plugins a repo needs.

list    print the stacks in stacks.json
detect  name the stacks whose marker files are in the repo
plan    show what apply would change, and change nothing
apply   enable a stack's plugins in the repo's .claude/settings.json

apply is additive. A plugin the repo already lists, on or off, is left as the
repo has it. When there is nothing to add, the settings file is not rewritten.
Nothing is installed here: the result carries the install commands to run.
"""
import argparse
import json
from pathlib import Path
import sys

TABLE = Path(__file__).resolve().parents[1] / 'stacks.json'


def die(msg):
    print(msg, file=sys.stderr)
    sys.exit(1)


def load_table(path):
    return json.loads(Path(path).read_text())['stacks']


def marker_present(root, marker):
    if marker.startswith('*.'):
        return any(root.glob(marker))
    if marker.endswith('/'):
        return (root / marker).is_dir()
    return (root / marker).is_file()


def detect(root, table):
    found = {}
    for name, stack in table.items():
        hits = [m for m in stack.get('detect', []) if marker_present(root, m)]
        if hits:
            found[name] = hits
    return found


def read_settings(path):
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        die(f'{path} is not valid JSON ({e}); fix it by hand, nothing was changed')
    if not isinstance(data, dict) or not isinstance(data.get('enabledPlugins', {}), dict):
        die(f'{path} has an unexpected shape; nothing was changed')
    return data


def plan(root, table, names):
    unknown = [n for n in names if n not in table]
    if unknown:
        die(f'unknown stack: {", ".join(unknown)} (known: {", ".join(table)})')
    path = root / '.claude' / 'settings.json'
    settings = read_settings(path)
    enabled = settings.get('enabledPlugins', {})
    add, already, kept_off, notes = [], [], [], []
    for name in names:
        for plugin in table[name]['plugins']:
            if plugin in add or plugin in already or plugin in kept_off:
                continue
            if plugin not in enabled:
                add.append(plugin)
            elif enabled[plugin]:
                already.append(plugin)
            else:
                kept_off.append(plugin)
        if table[name].get('note'):
            notes.append(f'{name}: {table[name]["note"]}')
    return path, settings, {
        'settings': str(path.relative_to(root)),
        'stacks': list(names),
        'add': add,
        'already_enabled': already,
        'kept_disabled': kept_off,
        'install_commands': [f'claude plugin install {p} --scope project' for p in add],
        'notes': notes,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--root', default='.')
    ap.add_argument('--table', default=str(TABLE))
    sub = ap.add_subparsers(dest='cmd', required=True)
    sub.add_parser('list')
    sub.add_parser('detect')
    for cmd in ('plan', 'apply'):
        p = sub.add_parser(cmd)
        p.add_argument('stacks', nargs='+')
    args = ap.parse_args()

    root = Path(args.root).resolve()
    table = load_table(args.table)

    if args.cmd == 'list':
        out = {n: {'label': s.get('label', ''), 'plugins': s['plugins']} for n, s in table.items()}
    elif args.cmd == 'detect':
        out = {'detected': detect(root, table)}
    else:
        path, settings, out = plan(root, table, args.stacks)
        out['status'] = 'planned'
        if args.cmd == 'apply':
            if out['add']:
                settings.setdefault('enabledPlugins', {}).update({p: True for p in out['add']})
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(settings, indent=2) + '\n')
                out['status'] = 'applied'
            else:
                out['status'] = 'unchanged'
    print(json.dumps(out, indent=2))


if __name__ == '__main__':
    main()
