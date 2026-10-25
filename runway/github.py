"""The few gh calls Runway makes. Tests swap in a fake with the same methods."""

import json
import subprocess

from .db import RunwayError


def gh(args, cwd):
    res = subprocess.run(['gh', *args], cwd=cwd, capture_output=True, text=True)
    if res.returncode != 0:
        raise RunwayError(f'gh {" ".join(args[:2])} failed: {(res.stderr or res.stdout).strip()[:400]}')
    return res.stdout


class GitHub:
    def create_pr(self, repo_path, base, branch, title, body):
        url = gh(['pr', 'create', '--draft', '--base', base, '--head', branch, '--title', title, '--body', body],
                 repo_path).strip()
        return int(url.rstrip('/').rsplit('/', 1)[-1])

    def pr(self, repo_path, number):
        return json.loads(gh(['pr', 'view', str(number), '--json',
                              'number,state,isDraft,headRefOid,headRefName,baseRefName,files,mergedAt'], repo_path))

    def checks(self, repo_path, number):
        """[{name, state}], or [] when the PR reports none. Pending checks come back as PENDING / IN_PROGRESS."""
        res = subprocess.run(['gh', 'pr', 'checks', str(number), '--json', 'name,state'], cwd=repo_path,
                             capture_output=True, text=True)
        if res.returncode not in (0, 8) or not res.stdout.strip():  # 8: some checks still pending
            return []
        return json.loads(res.stdout)

    def merge(self, repo_path, number, head, method='merge'):
        gh(['pr', 'ready', str(number)], repo_path)
        gh(['pr', 'merge', str(number), f'--{method}', '--match-head-commit', head], repo_path)

    def comment(self, repo_path, number, body):
        gh(['pr', 'comment', str(number), '--body', body], repo_path)
