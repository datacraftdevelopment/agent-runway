"""The merge gate for a chunk PR, as code. It trusts nothing a worker can edit.

Inputs: risk and the per-ticket verdicts from the journal (captured at start, raised
by review, never lowered), the PR's head and changed paths from GitHub, its checks
on that head, and runway.json as the default branch has it.
"""

import fnmatch
import json
import subprocess

from . import journal as jn

DEFAULT_SENSITIVE = (
    'runway.json', '.github/**', 'docs/maps/**/tickets/**',
    '**/auth/**', '**/*auth*', '**/payment*/**', '**/*payment*', '**/billing/**',
    '**/migrations/**', 'supabase/**', '**/*.sql',
    '.gitlab-ci.yml', '.circleci/**', 'Jenkinsfile', '**/Dockerfile',
)
CI_GREEN = ('SUCCESS', 'SKIPPED', 'NEUTRAL')


class GateError(Exception):
    pass


def run(args, cwd=None):
    out = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    if out.returncode != 0:
        raise GateError(f'{" ".join(args[:3])} failed: {(out.stderr or out.stdout).strip()}')
    return out.stdout


class GitHub:
    """The few gh calls the gate makes. Tests swap in a fake."""

    def pr(self, repo, number):
        return json.loads(run(['gh', 'pr', 'view', str(number), '--json',
                               'headRefOid,headRefName,baseRefName,state,isDraft,files'], cwd=repo))

    def checks(self, repo, number):
        out = subprocess.run(['gh', 'pr', 'checks', str(number), '--json', 'name,state'],
                             cwd=repo, capture_output=True, text=True)
        if out.returncode not in (0, 8) or not out.stdout.strip():  # 8 = some still pending
            return []
        return json.loads(out.stdout)

    def merge(self, repo, number, head, method):
        run(['gh', 'pr', 'ready', str(number)], cwd=repo)
        run(['gh', 'pr', 'merge', str(number), f'--{method}', '--match-head-commit', head], cwd=repo)


def repo_config(repo, base):
    """runway.json as the base branch has it, never as the chunk branch has it."""
    run(['git', '-C', repo, 'fetch', '--quiet', 'origin', base])
    out = subprocess.run(['git', '-C', repo, 'show', f'origin/{base}:runway.json'], capture_output=True, text=True)
    return json.loads(out.stdout) if out.returncode == 0 and out.stdout.strip() else {}


def sensitive_hits(paths, patterns):
    return sorted({p for p in paths for pat in patterns
                   if fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(p, pat.replace('**/', ''))})


def evaluate(data, pr, checks, config):
    """Decide without acting. Returns (verdict, reasons): 'merge' or 'needs-you'."""
    reasons = []
    head = pr['headRefOid']
    if pr['state'] != 'OPEN':
        reasons.append(f'the PR is {pr["state"].lower()}')
    if pr['headRefName'] != data['branch'] or pr['baseRefName'] != data['base']:
        reasons.append(f'the PR is {pr["headRefName"]} -> {pr["baseRefName"]}, not {data["branch"]} -> {data["base"]}')
    st = jn.states(data)
    open_tickets = [t for t, s in st.items() if s['state'] not in ('merged', 'dropped')]
    if open_tickets:
        reasons.append('tickets not merged into the chunk: ' + ', '.join(open_tickets))
    if any(s['state'] == 'dropped' for s in st.values()):
        reasons.append('a ticket was dropped, so the chunk is not what was approved')
    if jn.chunk_risk(data) != 'low':
        reasons.append('the chunk is not low risk (set at shaping, or raised in review)')
    review = next((e for e in reversed(data['events']) if e['kind'] == 'chunk-reviewed'), None)
    if not review or review['verdict'] != 'pass':
        reasons.append('no passing whole-chunk review')
    elif review['sha'] != head:
        reasons.append(f'the chunk review passed {review["sha"][:10]}, but the head is {head[:10]}')
    if not checks:
        reasons.append('no checks reported on the head commit')
    bad = [c['name'] for c in checks if c.get('state') not in CI_GREEN]
    if bad:
        reasons.append('checks not green: ' + ', '.join(bad))
    patterns = list(DEFAULT_SENSITIVE) + list(config.get('sensitive_paths', []))
    hits = sensitive_hits([f['path'] for f in pr.get('files', [])], patterns)
    if hits:
        reasons.append('sensitive paths changed: ' + ', '.join(hits[:8]))
    if config.get('auto_merge') is False:
        reasons.append('runway.json turns auto-merge off for this repo')
    return ('needs-you' if reasons else 'merge'), reasons


def gate(data, number, gh=None, act=False, config=None):
    gh = gh or GitHub()
    repo = data['repo']
    config = repo_config(repo, data['base']) if config is None else config
    pr = gh.pr(repo, number)
    verdict, reasons = evaluate(data, pr, gh.checks(repo, number), config)
    if verdict == 'merge' and act:
        gh.merge(repo, number, pr['headRefOid'], config.get('merge_method', 'merge'))
    return {'verdict': verdict, 'reasons': reasons, 'head': pr['headRefOid'], 'merged': verdict == 'merge' and act}
