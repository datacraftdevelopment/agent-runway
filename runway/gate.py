"""The merge gate for one ticket's PR, as code. It trusts nothing a worker can edit.

It merges on its own only when: the ticket is low risk (set at filing, possibly raised in review, never lowered), the
code review and the function review (two fresh sessions; on the other engine where there is one, else the same
engine) both passed on exactly the PR's head commit, every check on the PR is green, no changed path is sensitive,
and the repo's runway.json (as the base branch has it) doesn't turn auto-merge off. Anything else waits for the
person. From PR #3's gate.py.
"""

import fnmatch

DEFAULT_SENSITIVE = (
    'runway.json', '.github/**',
    '**/auth/**', '**/*auth*', '**/payment*/**', '**/*payment*', '**/billing/**',
    '**/migrations/**', 'supabase/**', '**/*.sql',
    '.gitlab-ci.yml', '.circleci/**', 'Jenkinsfile', '**/Dockerfile',
)
GREEN = ('SUCCESS', 'SKIPPED', 'NEUTRAL')
PENDING = ('PENDING', 'QUEUED', 'IN_PROGRESS', 'EXPECTED', 'WAITING', 'REQUESTED')


def sensitive_hits(paths, patterns):
    return sorted({p for p in paths for pat in patterns
                   if fnmatch.fnmatch(p, pat) or fnmatch.fnmatch(p, pat.replace('**/', ''))})


def evaluate(ticket, pr, checks, config, fresh=False):
    """Returns ('merged' | 'merge' | 'wait' | 'needs_you', reasons). `fresh`: the head was pushed moments ago, so
    no checks yet means CI hasn't started, not that there is none."""
    if pr['state'] == 'MERGED':
        return 'merged', []
    reasons = []
    if pr['state'] != 'OPEN':
        reasons.append(f'the PR is {pr["state"].lower()}')
    if ticket['risk'] != 'low':
        reasons.append('it is not low risk' + (' (raised in review)' if (ticket['review'] or '').endswith('risk raised')
                                               else ''))
    keys = ticket.keys() if hasattr(ticket, 'keys') else ticket
    reviews = {'code review': ticket['review'],
               'function review': ticket['function_review'] if 'function_review' in keys else None}
    missing = [name for name, text in reviews.items() if not (text or '').split(':')[-1].strip().startswith('pass')]
    if missing:
        reasons.append('no passing ' + ' or '.join(missing))
    elif ticket['sha'] != pr['headRefOid']:
        reasons.append(f'the reviews passed {(ticket["sha"] or "")[:7]}, but the PR head is {pr["headRefOid"][:7]}')
    patterns = list(DEFAULT_SENSITIVE) + list(config.get('sensitive_paths', []))
    hits = sensitive_hits([f['path'] for f in pr.get('files', [])], patterns)
    if hits:
        reasons.append('it changes sensitive paths: ' + ', '.join(hits[:6]))
    keys = ticket.keys() if hasattr(ticket, 'keys') else ticket
    if 'kind' in keys and ticket['kind'] == 'retro':
        reasons.append('it is a retro, which never merges on its own')
    if config.get('auto_merge') is False:
        reasons.append("the repo's runway.json turns auto-merge off")
    pending = [c['name'] for c in checks if c.get('state') in PENDING]
    if not reasons and pending:
        return 'wait', ['checks still running: ' + ', '.join(pending)]
    bad = [c['name'] for c in checks if c.get('state') not in GREEN + PENDING]
    if bad:
        reasons.append('checks failed: ' + ', '.join(bad))
    if not checks:
        if fresh and not reasons:
            return 'wait', ['waiting for checks to start']
        reasons.append('no checks reported on the PR')
    return ('needs_you' if reasons else 'merge'), reasons


def stop_reason(reasons):
    """Why the gate stopped a ticket, as one word for the stats' "where it stopped"."""
    text = ' '.join(reasons)
    if 'not low risk' in text:
        return 'not_low_risk'
    if 'sensitive paths' in text:
        return 'sensitive_path'
    if 'checks failed' in text or 'no checks' in text:
        return 'check'
    if 'review' in text:
        return 'review'
    return 'other'
