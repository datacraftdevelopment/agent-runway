"""This Mac as a runner: a fresh git worktree per run, the agent inside tmux so a closed app doesn't kill it.

Run files (prompt, log, exit code, outcome) live in ~/.runway/runs/<id>/, outside the worktree, so nothing of
Runway's ends up in a commit. Worktrees live in ~/.runway/worktrees/<repo>/<ticket>-<run>/.
"""

import shlex
import shutil
import subprocess
from pathlib import Path

from . import db


def git(*args, cwd, check=True):
    res = subprocess.run(['git', '-C', str(cwd), *args], capture_output=True, text=True)
    if check and res.returncode != 0:
        raise db.RunwayError(f'git {" ".join(args[:2])} failed: {(res.stderr or res.stdout).strip()[:400]}')
    return res


class LocalRunner:
    """Tests swap in a fake with the same methods."""

    def __init__(self, tmux='tmux'):
        self.tmux = tmux

    def capacity(self):
        """Memory, CPU and disk on this Mac right now (runway/capacity.py)."""
        from . import capacity
        return capacity.read(db.home())

    def run_dir(self, run_id):
        d = db.home() / 'runs' / str(run_id)
        d.mkdir(parents=True, exist_ok=True)
        return d

    def worktree(self, repo, ticket, run_id, ref, branch=None):
        """A clean checkout of `ref` (on `branch` when building, detached when reviewing)."""
        path = Path(repo['path'])
        # The base and the ticket's branch in two fetches: on a first build the branch isn't on GitHub yet, and one
        # fetch naming both fails whole, which left the worktree on a stale copy of the base.
        git('fetch', '--quiet', 'origin', repo['base'], cwd=path, check=False)
        if branch:
            git('fetch', '--quiet', 'origin', f'+refs/heads/{branch}:refs/remotes/origin/{branch}', cwd=path, check=False)
        wt = db.home() / 'worktrees' / repo['name'] / f'{ticket}-{run_id}'
        wt.parent.mkdir(parents=True, exist_ok=True)
        if branch:
            git('worktree', 'add', '--force', '-B', branch, str(wt), ref, cwd=path)
        else:
            git('worktree', 'add', '--force', '--detach', str(wt), ref, cwd=path)
        return wt

    def rev(self, repo, ref):
        res = git('rev-parse', '--verify', '--quiet', ref, cwd=repo['path'], check=False)
        return res.stdout.strip() or None

    def has_ref(self, repo, ref):
        return git('rev-parse', '--verify', '--quiet', ref, cwd=repo['path'], check=False).returncode == 0

    def start(self, name, workdir, line):
        res = subprocess.run([self.tmux, 'new-session', '-d', '-s', name, '-c', str(workdir), 'bash', '-lc', line],
                             capture_output=True, text=True)
        if res.returncode != 0:
            raise db.RunwayError(f'tmux could not start {name}: {res.stderr.strip()}')

    def alive(self, name):
        return subprocess.run([self.tmux, 'has-session', '-t', f'={name}'], capture_output=True).returncode == 0

    def stop(self, name):
        subprocess.run([self.tmux, 'kill-session', '-t', f'={name}'], capture_output=True)

    def check(self, workdir, cmd, timeout=900):
        """The repo's check command in the worktree. Returns (ok, the tail of its output)."""
        if not cmd:
            return True, 'no check command in runway.json'
        try:
            res = subprocess.run(cmd, shell=True, cwd=workdir, capture_output=True, text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return False, f'`{cmd}` ran past {timeout // 60} minutes'
        return res.returncode == 0, (res.stdout + res.stderr).strip()[-1500:]

    def commit(self, workdir, message):
        """Commit everything the worker changed. Returns the sha, or None when it changed nothing."""
        git('add', '-A', cwd=workdir)
        if git('diff', '--cached', '--quiet', cwd=workdir, check=False).returncode == 0:
            return None
        git('-c', 'user.name=Runway', '-c', 'user.email=runway@localhost', 'commit', '-q', '-m', message, cwd=workdir)
        return git('rev-parse', 'HEAD', cwd=workdir).stdout.strip()

    def head(self, workdir):
        return git('rev-parse', 'HEAD', cwd=workdir).stdout.strip()

    def push(self, workdir, branch):
        git('push', '--quiet', '--force-with-lease', 'origin', f'HEAD:refs/heads/{branch}', cwd=workdir)

    def remove(self, repo, workdir):
        if workdir and Path(workdir).exists():
            git('worktree', 'remove', '--force', str(workdir), cwd=repo['path'], check=False)
            shutil.rmtree(workdir, ignore_errors=True)

    def config(self, repo):
        """runway.json as the base branch has it on origin, never as a worker's branch has it."""
        import json
        res = git('show', f'origin/{repo["base"]}:runway.json', cwd=repo['path'], check=False)
        try:
            return json.loads(res.stdout) if res.returncode == 0 and res.stdout.strip() else {}
        except json.JSONDecodeError:
            return {}


def quote(s):
    return shlex.quote(str(s))
