"""First run on this Mac: what Runway needs, what is missing and the line that fixes it, linking the command into
Terminal, and a first repo's check command. The app's setup screen shows exactly what this reports.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

from . import db

# What each tool is for, and how a new user installs it.
TOOLS = [
    ('git', 'worktrees and commits', 'xcode-select --install'),
    ('gh', 'pull requests and merges', 'brew install gh'),
    ('tmux', 'keeps runs going when the app closes', 'brew install tmux'),
    ('claude', 'Claude Code, a worker and reviewer', 'curl -fsSL https://claude.ai/install.sh | bash'),
    ('codex', 'Codex, a worker and reviewer', 'npm install -g @openai/codex'),
]
SIGNINS = [
    ('claude', 'Claude Code', 'claude auth login'),
    ('codex', 'Codex', 'codex login'),
    ('github', 'GitHub', 'gh auth login'),
]
SKILLS_NOTE = ('The Runway skills (file tickets from a normal Claude Code or Codex session, guided setup) are not '
               'built yet. Until they are, file tickets with: runway file')


def login_shell(cmd, timeout=60):
    """A command as the person's login shell runs it, so PATH matches what they use in Terminal."""
    shell = os.environ.get('SHELL', '/bin/zsh')
    try:
        return subprocess.run([shell, '-lc', cmd], capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return subprocess.CompletedProcess(cmd, 124, '', f'timed out after {timeout}s')


def own_command():
    """bin/runway of this copy (inside Runway.app, or a checkout)."""
    return Path(__file__).resolve().parent.parent / 'bin' / 'runway'


def claude_signed_in():
    res = login_shell('claude auth status')
    try:
        return json.loads(res.stdout).get('loggedIn') is True
    except (json.JSONDecodeError, AttributeError):
        return False


def signed_in(name):
    if name == 'claude':
        return claude_signed_in()
    if name == 'codex':
        return login_shell('codex login status').returncode == 0
    return login_shell('gh auth status').returncode == 0


def report(con, check_signins=True):
    """Everything first run shows, and the setup row and agent sign-ins it records."""
    tools = []
    for name, why, fix in TOOLS:
        res = login_shell(f'command -v {name}')
        path = res.stdout.strip() if res.returncode == 0 else None
        tools.append({'name': name, 'ok': bool(path), 'path': path, 'why': why, 'fix': None if path else fix})
    have = {t['name'] for t in tools if t['ok']}
    need = {'claude': 'claude', 'codex': 'codex', 'github': 'gh'}
    signins = []
    for name, label, fix in SIGNINS:
        ok = need[name] in have and check_signins and signed_in(name)
        signins.append({'name': name, 'label': label, 'ok': ok,
                        'fix': None if ok else (fix if need[name] in have else f'install {need[name]} first')})
    ok = {s['name']: s['ok'] for s in signins}
    yes = lambda v: 'yes' if v else 'sign_in'
    con.execute('INSERT OR REPLACE INTO setup(runner, reachable, claude, codex, github, at) VALUES (?, ?, ?, ?, ?, ?)',
                ('This Mac', 'yes', yes(ok['claude']), yes(ok['codex']), yes(ok['github']), db.now()))
    for agent in ('claude', 'codex'):
        con.execute('UPDATE agents SET signed_in=? WHERE kind=?', (int(ok[agent]), agent))
    link = link_target()
    return {
        'command': {'path': str(own_command()), 'link': str(link), 'linked': is_our_link(link),
                    'link_dir_on_path': link_dir_on_path(link.parent)},
        'database': str(db.db_path()),
        'tools': tools,
        'signins': signins,
        'skills': {'built': False, 'note': SKILLS_NOTE},
        'repos': [r['name'] for r in con.execute('SELECT name FROM repos ORDER BY name')],
        'ready': all(t['ok'] for t in tools) and all(s['ok'] for s in signins),
    }


# ---- the command in Terminal ---------------------------------------------------------------------------------

def link_target(where=None):
    return Path(where).expanduser() / 'runway' if where else Path.home() / '.local' / 'bin' / 'runway'


def is_our_link(link):
    return link.is_symlink() and Path(os.readlink(link)).resolve() == own_command().resolve()


def link_dir_on_path(folder):
    res = login_shell('echo "$PATH"')
    return str(folder) in res.stdout.strip().split(':')


def install_command(where=None):
    """A symlink to this copy's runway, in ~/.local/bin unless told otherwise. Never replaces anything else."""
    link = link_target(where)
    if is_our_link(link):
        return f'{link} already points at this Runway'
    if link.exists() or link.is_symlink():
        raise db.RunwayError(f'{link} already exists and is not this Runway; move it or pass --to <folder>')
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(own_command())
    note = '' if link_dir_on_path(link.parent) else (f'; add {link.parent} to your PATH '
                                                       f'(echo \'export PATH="{link.parent}:$PATH"\' >> ~/.zprofile)')
    return f'linked {link} -> {own_command()}{note}'


# ---- a first repo ----------------------------------------------------------------------------------------------

def suggest_check(path):
    """A likely test command for a clone, from what is in it; None when nothing says."""
    p = Path(path)
    cfg = p / 'runway.json'
    if cfg.exists():
        try:
            cmd = json.loads(cfg.read_text()).get('check_cmd')
            if cmd:
                return cmd
        except json.JSONDecodeError:
            pass
    if (p / 'package.json').exists():
        try:
            if 'test' in json.loads((p / 'package.json').read_text()).get('scripts', {}):
                return 'npm test'
        except json.JSONDecodeError:
            pass
    if (p / 'Package.swift').exists():
        return 'swift test'
    if (p / 'Cargo.toml').exists():
        return 'cargo test'
    if (p / 'go.mod').exists():
        return 'go test ./...'
    if (p / 'pyproject.toml').exists() and shutil.which('pytest'):
        return 'pytest -q'
    if (p / 'tests').is_dir() and any((p / 'tests').glob('*.py')):
        return 'python3 -m unittest -q'
    if (p / 'Makefile').exists() and 'test:' in (p / 'Makefile').read_text(errors='replace'):
        return 'make test'
    return None
