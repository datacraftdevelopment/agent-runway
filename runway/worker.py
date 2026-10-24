"""What a headless worker is told and how it is started: the prompt, and the claude / codex command line.

Workers never push, open PRs or merge: the loop does those, as code, after reading the worker's outcome file. A build
worker edits files and runs the repo's check; a reviewer reads and runs. Each writes one JSON file the loop reads back.

Permissions, kept as small as the job allows:
  Claude Code: --permission-mode dontAsk with an allow-list (file tools, read-only git, the repo's check commands, and
               writing its outcome file). Anything else is refused, not asked.
  Codex:       its own workspace-write sandbox: writes only inside the worktree and the run folder, no network.
"""

import json
import shlex
import uuid

BUILD = """\
You are a Runway worker. Nobody is watching this session: work alone, then stop.

Ticket {id}: {title}
Repo: {repo}, in this folder (a fresh worktree started from {start}).

## The ticket

{body}

## Acceptance (every line must pass)

{acceptance}
{note}
## How to work

1. Read what you need in this folder. Change only what this ticket asks for.
2. Build it, test-first where the repo has tests. Run the repo's check: `{check}`.
3. Do not commit, push, open a PR or merge: Runway does those after you finish. Never edit runway.json or CI config.
4. Never weaken, skip or delete a test to get green.
5. If you are truly blocked on a decision only the person can make, stop and ask one crisp question (below) with
   the option you recommend. Otherwise make the call and say why in your summary.

## When you finish

Write exactly one JSON file to {outcome} and then stop:

{{"status": "done", "summary": "what you built and the check result"}}
{{"status": "needs_you", "question": "one question", "recommended": "the option you recommend", "summary": "..."}}
{{"status": "failed", "summary": "what went wrong and the last good step"}}

"done" only when the check passes and every Acceptance line holds.
"""

REVIEW = """\
You are a Runway reviewer: the other agent from the one that built this. You read and run; you never edit, commit or
push. Nobody is watching this session: review, write your verdict file, stop.

Ticket {id}: {title}
Repo: {repo}. This folder is checked out at commit {sha}, the exact commit you are reviewing.
See the change with: git diff {base_ref}...HEAD

## The ticket

{body}

## Acceptance

{acceptance}

## How to review

1. Read the diff and the code around it.
2. Run the repo's check: `{check}`, and anything an Acceptance line says to verify.
3. Judge on three things only: every Acceptance line holds at this commit; it does what the ticket says and nothing it
   doesn't; and no lowered bar (skipped, deleted or weakened tests, stubs, loosened checks). A finding names a
   file:line and what it breaks. Style preferences are notes, not findings.
4. Risk only rises: say "not_low" if the change touches anything risky the ticket didn't expect (auth, money, data,
   migrations, CI, secrets, a public interface). Otherwise repeat the ticket's risk: {risk}.

## When you finish

Write exactly one JSON file to {outcome} and then stop:

{{"verdict": "pass", "risk": "{risk}", "sha": "{sha}", "findings": [], "summary": "what you checked and saw"}}

"verdict" is "pass" or "fail"; "sha" is the commit you reviewed.
"""


def acceptance_lines(t):
    lines = json.loads(t['acceptance'] or '[]')
    return '\n'.join(f'- {a}' for a in lines) or '- (none given)'


def build_prompt(t, repo, start, check, outcome):
    note = f'\n## Note for this run\n\n{t["note"]}\n' if t['note'] else ''
    return BUILD.format(id=t['id'], title=t['title'], repo=repo, start=start, body=t['body'] or '(no body)',
                        acceptance=acceptance_lines(t), note=note, check=check or 'the repo\'s tests', outcome=outcome)


def review_prompt(t, repo, sha, base_ref, check, outcome):
    return REVIEW.format(id=t['id'], title=t['title'], repo=repo, sha=sha, base_ref=base_ref,
                         body=t['body'] or '(no body)', acceptance=acceptance_lines(t),
                         check=check or 'the repo\'s tests', risk=t['risk'], outcome=outcome)


def allowed_tools(check_commands, run_dir):
    """Claude Code's allow-list: file tools, read-only git, the repo's check commands."""
    tools = ['Read', 'Edit', 'Write', 'Glob', 'Grep',
             'Bash(git status:*)', 'Bash(git diff:*)', 'Bash(git log:*)', 'Bash(git show:*)',
             'Bash(ls:*)', 'Bash(pwd)']
    tools += [f'Bash({c}:*)' for c in check_commands if c]
    return tools


def command(agent, prompt_file, run_dir, workdir, check_commands, session_id=None):
    """The shell line tmux runs: the agent, its log, then its exit code, so the loop can read both later."""
    log = shlex.quote(str(run_dir / 'log'))
    done = shlex.quote(str(run_dir / 'exit'))
    prompt = f'"$(cat {shlex.quote(str(prompt_file))})"'
    if agent == 'claude':
        tools = ' '.join(shlex.quote(t) for t in allowed_tools(check_commands, run_dir))
        line = (f'claude -p {prompt} --session-id {session_id} --permission-mode dontAsk '
                f'--add-dir {shlex.quote(str(run_dir))} --allowedTools {tools} --output-format json')
    elif agent == 'codex':
        line = (f'codex exec -s workspace-write --add-dir {shlex.quote(str(run_dir))} --json '
                f'-C {shlex.quote(str(workdir))} -o {shlex.quote(str(run_dir / "last-message.txt"))} {prompt}')
    else:
        raise ValueError(agent)
    return f'{line} > {log} 2>&1; echo $? > {done}'


def new_session_id():
    return str(uuid.uuid4())


def codex_session(log_text):
    """Codex prints its session (thread) id in its first --json event."""
    for line in log_text.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        for key in ('thread_id', 'session_id', 'conversation_id'):
            if isinstance(ev, dict) and ev.get(key):
                return ev[key]
            if isinstance(ev, dict) and isinstance(ev.get('msg'), dict) and ev['msg'].get(key):
                return ev['msg'][key]
    return None
