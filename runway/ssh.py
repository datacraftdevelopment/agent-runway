"""Another Mac as a runner, over plain ssh: the same worktree + tmux + outcome file as this Mac, run there.

The loop keeps every run's folder on this Mac (it reads the log, exit code and outcome from it), so the runner
mirrors it: `start` sends the folder over before the agent starts, and the loop calls `collect` to bring it back once
the session has ended. Neither keeps anything in memory, so a restarted loop still collects runs started before. Paths under this Mac's ~/.runway are rewritten to the other Mac's in the shell line and the prompt.

On the other Mac, Runway keeps its own clone of each repo (~/.runway/repos/<name>, cloned from this Mac's origin
URL) and its worktrees (~/.runway/worktrees/<repo>/<ticket>-<run>/). Pushes go from there, so that Mac needs push
access to the repo, as well as Claude Code or Codex signed in for a non-interactive login shell.
"""

import io
import json
import shlex
import subprocess
import tarfile
from pathlib import Path

from . import db
from .runner import git

UNREACHABLE = 255          # ssh's own exit code when it couldn't connect or the connection dropped
TEXT_FILES = {'prompt.md'}  # files in a run folder that carry this Mac's paths


def q(s):
    return shlex.quote(str(s))


class SSHRunner:
    """The runner interface of LocalRunner, with every git, tmux and check command run on `host`."""

    def __init__(self, host, ssh='ssh', tmux='tmux', options=('-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10')):
        self.host = host
        self.ssh = [ssh, *options]
        self.tmux = tmux
        self._root = None

    # ---- talking to the other Mac --------------------------------------------------------------------------------

    def sh(self, script, input=None, timeout=120, text=True):
        """`script` in a login shell on the other Mac (so PATH has claude, codex and tmux)."""
        try:
            return subprocess.run([*self.ssh, self.host, f'bash -lc {q(script)}'], input=input, capture_output=True,
                                  text=text, timeout=timeout)
        except subprocess.TimeoutExpired:
            return subprocess.CompletedProcess([], UNREACHABLE, '' if text else b'', f'ssh {self.host} timed out')

    def must(self, script, what, **kw):
        res = self.sh(script, **kw)
        if res.returncode != 0:
            err = res.stderr if isinstance(res.stderr, str) else res.stderr.decode(errors='replace')
            out = res.stdout if isinstance(res.stdout, str) else res.stdout.decode(errors='replace')
            raise db.RunwayError(f'{what} on {self.host} failed: {(err or out).strip()[:400]}')
        return res

    def root(self):
        """The other Mac's ~/.runway, asked for once."""
        if self._root is None:
            home = self.must('printf %s "$HOME"', 'reading $HOME').stdout.strip()
            if not home:
                raise db.RunwayError(f'{self.host} did not say where its home folder is')
            self._root = f'{home}/.runway'
        return self._root

    def there(self, text):
        """This Mac's ~/.runway paths, as the other Mac has them."""
        return text.replace(str(db.home()), self.root())

    def git(self, repo_dir, *args, check=True):
        res = self.sh(f'git -C {q(repo_dir)} ' + ' '.join(q(a) for a in args))
        if check and res.returncode != 0:
            raise db.RunwayError(f'git {" ".join(args[:2])} on {self.host} failed: '
                                 f'{(res.stderr or res.stdout).strip()[:400]}')
        return res

    def clone(self, repo):
        """The other Mac's clone of `repo`, made on first use from this Mac's origin URL."""
        path = f'{self.root()}/repos/{repo["name"]}'
        url = git('remote', 'get-url', 'origin', cwd=repo['path']).stdout.strip()
        self.must(f'test -d {q(path)}/.git || git clone --quiet {q(url)} {q(path)}', f'cloning {repo["name"]}',
                  timeout=900)
        return path

    # ---- the runner interface ------------------------------------------------------------------------------------

    def run_dir(self, run_id):
        d = db.home() / 'runs' / str(run_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def worktree(self, repo, ticket, run_id, ref, branch=None):
        path = self.clone(repo)
        fetch = [repo['base']] + ([f'+refs/heads/{branch}:refs/remotes/origin/{branch}'] if branch else [])
        self.git(path, 'fetch', '--quiet', 'origin', *fetch, check=False)
        wt = f'{self.root()}/worktrees/{repo["name"]}/{ticket}-{run_id}'
        self.must(f'mkdir -p {q(str(Path(wt).parent))}', 'making the worktrees folder')
        if branch:
            self.git(path, 'worktree', 'add', '--force', '-B', branch, wt, ref)
        else:
            self.git(path, 'worktree', 'add', '--force', '--detach', wt, ref)
        return wt

    def rev(self, repo, ref):
        res = self.git(self.clone(repo), 'rev-parse', '--verify', '--quiet', ref, check=False)
        return res.stdout.strip() or None

    def has_ref(self, repo, ref):
        return self.git(self.clone(repo), 'rev-parse', '--verify', '--quiet', ref, check=False).returncode == 0

    def start(self, name, workdir, line):
        local = run_folder(line)
        if local:
            remote = self.there(str(local))
            self.must(f'mkdir -p {q(remote)} && tar -C {q(remote)} -xf -', 'sending the run folder',
                      input=self.pack(local), text=False)
        res = self.sh(f'{self.tmux} new-session -d -s {q(name)} -c {q(workdir)} bash -lc {q(self.there(line))}')
        if res.returncode != 0:
            raise db.RunwayError(f'tmux on {self.host} could not start {name}: {res.stderr.strip()}')

    def alive(self, name):
        res = self.sh(f'{self.tmux} has-session -t {q("=" + name)}')
        if res.returncode == UNREACHABLE:
            return True        # can't tell: keep waiting, and the loop's hour limit still applies
        return res.returncode == 0

    def stop(self, name):
        self.sh(f'{self.tmux} kill-session -t {q("=" + name)}')

    def check(self, workdir, cmd, timeout=900):
        if not cmd:
            return True, 'no check command in runway.json'
        res = self.sh(f'cd {q(workdir)} && {cmd}', timeout=timeout)
        if res.returncode == UNREACHABLE and 'timed out' in (res.stderr or ''):
            return False, f'`{cmd}` ran past {timeout // 60} minutes'
        return res.returncode == 0, (res.stdout + res.stderr).strip()[-1500:]

    def commit(self, workdir, message):
        self.git(workdir, 'add', '-A')
        if self.git(workdir, 'diff', '--cached', '--quiet', check=False).returncode == 0:
            return None
        self.git(workdir, '-c', 'user.name=Runway', '-c', 'user.email=runway@localhost', 'commit', '-q', '-m', message)
        return self.head(workdir)

    def head(self, workdir):
        return self.git(workdir, 'rev-parse', 'HEAD').stdout.strip()

    def push(self, workdir, branch):
        self.git(workdir, 'push', '--quiet', '--force-with-lease', 'origin', f'HEAD:refs/heads/{branch}')

    def remove(self, repo, workdir):
        if workdir:
            self.git(f'{self.root()}/repos/{repo["name"]}', 'worktree', 'remove', '--force', workdir, check=False)
            self.sh(f'rm -rf {q(workdir)}')

    def config(self, repo):
        res = self.git(self.clone(repo), 'show', f'origin/{repo["base"]}:runway.json', check=False)
        try:
            return json.loads(res.stdout) if res.returncode == 0 and res.stdout.strip() else {}
        except json.JSONDecodeError:
            return {}

    # ---- the run folder, both ways -------------------------------------------------------------------------------

    def pack(self, folder):
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode='w') as tar:
            for f in sorted(Path(folder).iterdir()):
                if not f.is_file():
                    continue
                data = f.read_bytes()
                if f.name in TEXT_FILES:
                    data = self.there(data.decode()).encode()
                info = tarfile.TarInfo(f.name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return buf.getvalue()

    def collect(self, run_dir):
        """Bring a finished run's folder back to this Mac, so the loop reads its log, exit code and outcome. The
        prompt stays as this Mac wrote it. Quietly does nothing when the folder can't be read there."""
        local = Path(run_dir)
        res = self.sh(f'tar -C {q(self.there(str(local)))} -cf - .', text=False)
        if res.returncode != 0:
            return
        with tarfile.open(fileobj=io.BytesIO(res.stdout)) as tar:
            for m in tar.getmembers():
                if m.isfile() and '/' not in m.name.removeprefix('./') and m.name.removeprefix('./') not in TEXT_FILES:
                    (local / m.name.removeprefix('./')).write_bytes(tar.extractfile(m).read())


def run_folder(line):
    """The run folder named in a worker's shell line (where its log goes), or None."""
    runs = db.home() / 'runs'
    try:
        words = shlex.split(line)
    except ValueError:
        return None
    for w in words:
        p = Path(w)
        if p.name == 'log' and runs in p.parents:
            return p.parent
    return None
