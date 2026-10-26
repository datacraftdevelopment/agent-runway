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
PLUGIN = 'agent-runway'          # the plugin and its marketplace share this name


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


ENGINES = ('claude', 'codex')


def report(con, check_signins=True):
    """Everything first run shows, and the setup row and agent sign-ins it records.

    One engine is enough: Claude Code or Codex, signed in, is a full green. The other one, when it is missing, is
    marked optional rather than failed, and ready doesn't wait for it."""
    tools = []
    for name, why, fix in TOOLS:
        res = login_shell(f'command -v {name}')
        path = res.stdout.strip() if res.returncode == 0 else None
        tools.append({'name': name, 'ok': bool(path), 'path': path, 'why': why, 'fix': None if path else fix,
                      'optional': False})
    have = {t['name'] for t in tools if t['ok']}
    need = {'claude': 'claude', 'codex': 'codex', 'github': 'gh'}
    signins = []
    for name, label, fix in SIGNINS:
        ok = need[name] in have and check_signins and signed_in(name)
        signins.append({'name': name, 'label': label, 'ok': ok, 'optional': False,
                        'fix': None if ok else (fix if need[name] in have else f'install {need[name]} first')})
    ok = {s['name']: s['ok'] for s in signins}
    engines = [e for e in ENGINES if ok[e]]
    if engines:
        # With one engine ready, the other is optional: shown without a red mark, never blocking.
        for row in tools + signins:
            if row['name'] in ENGINES and not ok[row['name']]:
                row['optional'] = True
    mark = lambda name: 'yes' if ok[name] else ('optional' if name in ENGINES and engines else 'sign_in')
    con.execute('INSERT OR REPLACE INTO setup(runner, reachable, claude, codex, github, at) VALUES (?, ?, ?, ?, ?, ?)',
                ('This Mac', 'yes', mark('claude'), mark('codex'), mark('github'), db.now()))
    for agent in ENGINES:
        con.execute('UPDATE agents SET signed_in=? WHERE kind=?', (int(ok[agent]), agent))
    link = link_target()
    return {
        'command': {'path': str(own_command()), 'link': str(link), 'linked': is_our_link(link),
                    'link_dir_on_path': link_dir_on_path(link.parent)},
        'database': str(db.db_path()),
        'database_exists': db.db_path().exists(),
        'tools': tools,
        'signins': signins,
        'engines': engines,
        'skills': skills_status(),
        'repos': [r['name'] for r in con.execute('SELECT name FROM repos ORDER BY name')],
        'ready': bool(engines) and all(r['ok'] or r['optional'] for r in tools + signins),
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

def tree(path, ref=None):
    """The clone's files (to two levels) and a reader for them: from `ref` in git (origin's base, what Runway
    builds from) when it exists, else the folder on disk."""
    p = Path(path)
    if ref:
        res = subprocess.run(['git', '-C', str(p), 'ls-tree', '-r', '--name-only', ref], capture_output=True, text=True)
        if res.returncode == 0:
            names = {n for n in res.stdout.splitlines() if n.count('/') <= 1}

            def read(rel):
                out = subprocess.run(['git', '-C', str(p), 'show', f'{ref}:{rel}'], capture_output=True, text=True)
                return out.stdout if out.returncode == 0 else ''
            return names, read
    names = set()
    for f in p.iterdir() if p.is_dir() else []:
        if f.name.startswith('.') and f.name != '.gitignore':
            continue
        names.add(f.name)
        if f.is_dir() and f.name not in ('node_modules', 'build', 'dist', 'vendor'):
            names.update(f'{f.name}/{g.name}' for g in f.iterdir())
    return names, lambda rel: (p / rel).read_text(errors='replace') if (p / rel).is_file() else ''


def suggest_commands(path, ref=None):
    """What Runway's sessions should be allowed to run in a clone: the check (tests) first, then the build and run
    commands the work needs. Looks at the top and one folder down (a Swift package in a subfolder, say), on `ref`
    (origin's base branch) when given. runway.json's own lists, when it has one, come first."""
    names, read = tree(path, ref)
    check, allow = None, []

    def add(cmd):
        if cmd and cmd not in allow:
            allow.append(cmd)
    if 'runway.json' in names:
        try:
            data = json.loads(read('runway.json') or '{}')
            check = data.get('check_cmd') or None
            for c in data.get('worker_commands', []):
                add(c)
        except json.JSONDecodeError:
            pass
    dirs = [''] + sorted({n.split('/')[0] for n in names if '/' in n and not n.startswith('.')
                          and n.split('/')[0] not in ('node_modules', 'build', 'dist', 'vendor')})
    has = lambda d, f: (f'{d}/{f}' if d else f) in names
    for d in dirs:
        if has(d, 'Package.swift'):
            flag = f' --package-path {d}' if d else ''
            check = check or f'swift test{flag}'
            for c in (f'swift test{flag}', f'swift build{flag}', f'swift run{flag}'):
                add(c)
        if has(d, 'package.json'):
            try:
                scripts = json.loads(read(f'{d}/package.json' if d else 'package.json') or '{}').get('scripts', {})
            except json.JSONDecodeError:
                scripts = {}
            pre = f'npm --prefix {d} ' if d else 'npm '
            if 'test' in scripts:
                check = check or f'{pre}test'
                add(f'{pre}test')
            if 'build' in scripts:
                add(f'{pre}run build')
        if has(d, 'uv.lock') or (has(d, 'pyproject.toml') and shutil.which('uv')):
            check = check or ('uv run pytest' if not d else f'uv run --project {d} pytest')
            add('uv run')
        elif has(d, 'pyproject.toml') and shutil.which('pytest'):
            check = check or 'pytest -q'
            add('pytest')
        if has(d, 'Cargo.toml'):
            check = check or 'cargo test'
            add('cargo test')
            add('cargo build')
        if has(d, 'go.mod'):
            check = check or 'go test ./...'
            add('go test')
            add('go build')
        if has(d, 'Makefile') and 'test:' in read(f'{d}/Makefile' if d else 'Makefile'):
            check = check or ('make test' if not d else f'make -C {d} test')
            add('make')
    if not check and any(n.startswith('tests/') and n.endswith('.py') for n in names):
        check = 'python3 -m unittest -q'
    if check:
        add(check)
    return {'check': check, 'commands': [c for c in allow if c != check]}


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


# ---- the skills ------------------------------------------------------------------------------------------------

def plugin_dir():
    """The marketplace folder shipped with this copy: plugin/ in a checkout, cli/plugin/ inside Runway.app."""
    return Path(__file__).resolve().parent.parent / 'plugin'


def plugin_list(agent):
    res = login_shell('claude plugin list' if agent == 'claude' else 'codex plugin list')
    return res.stdout if res.returncode == 0 else ''


def installed_in(agent):
    """Whether the agent-runway plugin is installed in Claude Code or Codex, as their own plugin lists say."""
    return f'{PLUGIN}@{PLUGIN}' in plugin_list(agent)


def installed_version(agent, listing=None):
    """The agent-runway version Claude Code or Codex has installed, from its plugin list; None if not installed.

    Claude Code prints a block per plugin ("❯ agent-runway@agent-runway" then "Version: 0.2.0"); Codex prints a table
    row ("agent-runway@agent-runway  installed, enabled  0.2.0  <source>")."""
    import re
    text = plugin_list(agent) if listing is None else listing
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if f'{PLUGIN}@{PLUGIN}' not in line:
            continue
        if agent == 'claude':
            for after in lines[i + 1:i + 6]:
                m = re.match(r'\s*Version:\s*(\S+)', after)
                if m:
                    return m.group(1)
        else:
            m = re.search(r'\s(\d+(?:\.\d+)+)\s', line + ' ')
            if m:
                return m.group(1)
        return 'unknown'
    return None


def bundled_version():
    """The skills version this copy of Runway carries (plugin.json)."""
    try:
        return json.loads((plugin_dir() / PLUGIN / '.claude-plugin' / 'plugin.json').read_text()).get('version')
    except (OSError, ValueError):
        return None


def version_key(v):
    try:
        return tuple(int(x) for x in v.split('-')[0].split('.'))
    except (AttributeError, ValueError):
        return ()


def older(installed, bundled):
    """An installed version older than the one this Runway carries. One the agent's list doesn't show a readable
    version for is left alone: if its output changes shape, Runway shouldn't reinstall on every check."""
    if not installed or not bundled or installed == 'unknown':
        return False
    return version_key(installed) < version_key(bundled)


def skills_status():
    built = (plugin_dir() / PLUGIN / 'skills').is_dir()
    have = {a: bool(shutil.which(a) or login_shell(f'command -v {a}').returncode == 0) for a in ('claude', 'codex')}
    versions = {a: installed_version(a) if built and have[a] else None for a in ('claude', 'codex')}
    status = {a: versions[a] is not None for a in ('claude', 'codex')}
    bundled = bundled_version()
    stale = [a for a in ('claude', 'codex') if older(versions[a], bundled)]
    names = {'claude': 'Claude Code', 'codex': 'Codex'}
    present = [a for a in ('claude', 'codex') if have[a]]
    if not built:
        note = 'This copy of Runway has no skills folder.'
    elif not present:
        note = 'Install Claude Code or Codex first; the skills go into whichever you use.'
    elif stale:
        note = (f'The skills in {" and ".join(names[a] for a in stale)} are older ('
                + ', '.join(versions[a] for a in stale) + f') than this Runway\'s {bundled}: runway install-skills '
                'updates them.')
    elif all(status[a] for a in present):
        note = 'The Agent Runway skills are in ' + ' and '.join(names[a] for a in present) + '.'
    else:
        missing = ' and '.join(names[a] for a in present if not status[a])
        note = f'Not in {missing} yet: runway install-skills adds them.'
    # installed: in every engine this Mac has (one is enough). outdated: some engine has an older version.
    return {'built': built, 'claude': status['claude'], 'codex': status['codex'], 'path': str(plugin_dir()),
            'installed': bool(present) and all(status[a] for a in present), 'note': note,
            'version': bundled, 'claude_version': versions['claude'], 'codex_version': versions['codex'],
            'outdated': bool(stale)}


def install_skills(agents=('claude', 'codex')):
    """Adds Runway's marketplace (the folder shipped with this copy) to each agent and installs the plugin from it,
    through the agent's own plugin commands. When an older version is installed (an app update brought newer skills),
    it updates it instead. Safe to run again."""
    src = plugin_dir()
    if not (src / PLUGIN / 'skills').is_dir():
        raise db.RunwayError(f'no skills in {src}')
    done = []
    for agent in agents:
        if login_shell(f'command -v {agent}').returncode != 0:
            done.append(f'{agent}: not installed, skipped')
            continue
        q = shlex_quote(str(src))
        had = installed_version(agent)
        stale = older(had, bundled_version())
        if agent == 'claude':
            steps = [f'claude plugin marketplace add {q}']
            steps += ([f'claude plugin marketplace update {PLUGIN}', f'claude plugin update {PLUGIN}@{PLUGIN}']
                      if stale else [f'claude plugin install {PLUGIN}@{PLUGIN}'])
        else:
            # Codex keeps its own copy of a local marketplace's plugin: remove and add again picks up the new one.
            steps = [f'codex plugin marketplace add {q}']
            steps += ([f'codex plugin remove {PLUGIN}@{PLUGIN}'] if stale else []) + [f'codex plugin add {PLUGIN}@{PLUGIN}']
        for step in steps:
            res = login_shell(step, timeout=120)
            said = (res.stdout + res.stderr).strip()
            if res.returncode != 0 and 'already' not in said.lower():
                raise db.RunwayError(f'{step} failed: {said[-300:]}')
        now = installed_version(agent)
        if not now:
            done.append(f'{agent}: ran the install, but its plugin list does not show {PLUGIN} yet')
        elif stale:
            done.append(f'{agent}: updated {PLUGIN} from {had} to {now}' + ('' if not older(now, bundled_version())
                        else f' (still older than {bundled_version()}; restart {agent} and run it again)'))
        else:
            done.append(f'{agent}: installed {PLUGIN} {now} from {src}')
    return '\n'.join(done)


def shlex_quote(s):
    import shlex
    return shlex.quote(s)
