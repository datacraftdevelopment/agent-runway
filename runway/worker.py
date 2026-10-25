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

Shell commands: run each one on its own, exactly as written, with nothing chained (no &&, ;, | or cd in front; this
folder is already the repo). Only these are allowed: {allowed}. If one is refused, run it again on its own.

## When you finish

Write exactly one JSON file to {outcome} and then stop:

{{"status": "done", "summary": "what you built and the check result"}}
{{"status": "needs_you", "question": "one question", "recommended": "the option you recommend", "summary": "..."}}
{{"status": "failed", "summary": "what went wrong and the last good step"}}

"done" only when the check passes and every Acceptance line holds.
"""

# Review is two fresh sessions, each with its own prompt and none of the builder's context (Joe, 2026-10-25).
REVIEW_HEAD = """\
You are a Runway {role_name}, in a fresh session: you didn't build this and you have none of the builder's context.
You read and run; you never edit, commit or push. Nobody is watching this session: review, write your verdict file,
stop.

Ticket {id}: {title}
Repo: {repo}. This folder is checked out at commit {sha}, the exact commit you are reviewing.
See the change with: git diff {base_ref}...HEAD

## The ticket

{body}

## Acceptance

{acceptance}

"""

REVIEW_CODE = """\
## How to review the code

1. Read the diff and the code around it.
2. Judge: correctness and bugs (edge cases, error paths, anything that breaks existing behaviour); risk; sensitive
   paths (auth, payments, data and migrations, CI, secrets, a public interface); and tests worth having that are
   missing. Also any lowered bar: skipped, deleted or weakened tests, stubs, loosened checks. That fails it.
3. A finding names a file:line and what it breaks. Style preferences are notes, not findings.
4. Risk only rises: say "not_low" if the change touches anything risky the ticket didn't expect. Otherwise repeat the
   ticket's risk: {risk}.
{rules}
## When you finish

Write exactly one JSON file to {outcome} and then stop:

{{"verdict": "pass", "risk": "{risk}", "sha": "{sha}", "findings": [], "summary": "what you read and saw"}}

"verdict" is "pass" or "fail"; "sha" is the commit you reviewed.
"""

REVIEW_FUNCTION = """\
## How to review the function

1. Run the repo's check: `{check}`. It must pass.
2. Walk each Acceptance line above, in order: do what its Verify says (run the command, or exercise the behaviour
   it describes) at this commit, and record pass or fail with the evidence (the command and what it printed, or what
   you saw). A line you can't verify here is a fail, with the reason.
3. Pass only when the check passes and every Acceptance line passes. Risk only rises: say "not_low" if running it
   showed something risky the ticket didn't expect. Otherwise repeat the ticket's risk: {risk}.
{rules}
## When you finish

Write exactly one JSON file to {outcome} and then stop:

{{"verdict": "pass", "risk": "{risk}", "sha": "{sha}", "check": "pass",
  "lines": [{{"line": "A1: ...", "pass": true, "evidence": "the command and its output"}}],
  "summary": "what you ran and saw"}}

"verdict" is "pass" or "fail"; "sha" is the commit you reviewed; one entry in "lines" per Acceptance line.
"""

REVIEW_RULES = """
Shell commands: run each one on its own, exactly as written, with nothing chained (no &&, ;, | or cd in front; this
folder is already the repo). Only these are allowed: {allowed}. If one is refused, run it again on its own.
"""

ROLES = ('code', 'function')
ROLE_NAMES = {'code': 'code reviewer', 'function': 'function reviewer'}


def acceptance_lines(t):
    lines = json.loads(t['acceptance'] or '[]')
    return '\n'.join(f'- {a}' for a in lines) or '- (none given)'


def allowed_list(check_commands):
    """The shell commands a worker may run, as the prompt lists them."""
    cmds = ['git status', 'git diff ...', 'git log ...', 'git show ...', 'ls ...'] + [c for c in check_commands if c]
    return ', '.join(f'`{c}`' for c in cmds)


def build_prompt(t, repo, start, check, outcome, check_commands=()):
    note = f'\n## Note for this run\n\n{t["note"]}\n' if t['note'] else ''
    return BUILD.format(id=t['id'], title=t['title'], repo=repo, start=start, body=t['body'] or '(no body)',
                        acceptance=acceptance_lines(t), note=note, check=check or 'the repo\'s tests', outcome=outcome,
                        allowed=allowed_list(check_commands or [check]))


def review_prompt(t, repo, sha, base_ref, check, outcome, check_commands=(), role='code'):
    fields = dict(id=t['id'], title=t['title'], repo=repo, sha=sha, base_ref=base_ref, body=t['body'] or '(no body)',
                  acceptance=acceptance_lines(t), check=check or 'the repo\'s tests', risk=t['risk'],
                  outcome=outcome, role_name=ROLE_NAMES[role])
    rules = REVIEW_RULES.format(allowed=allowed_list(check_commands or [check]))
    body = (REVIEW_CODE if role == 'code' else REVIEW_FUNCTION).format(rules=rules, **fields)
    return REVIEW_HEAD.format(**fields) + body


def function_findings(verdict):
    """The failing Acceptance lines of a function review, as findings a fix pass can act on."""
    out = [f'{x.get("line", "?")}: {x.get("evidence", "no evidence given")}'
           for x in verdict.get('lines') or [] if not x.get('pass')]
    if str(verdict.get('check', 'pass')).lower() != 'pass':
        out.insert(0, 'the check command failed')
    return out


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


def usage(agent, log_text):
    """(tokens in, tokens out, cost in USD) from a run's log, as the agent reported them. Claude Code's JSON carries
    a dollar cost; Codex reports tokens only, so its cost stays None. Nothing is estimated."""
    if agent == 'claude':
        try:
            data = json.loads(log_text.strip().splitlines()[-1] if log_text.strip() else '{}')
        except (json.JSONDecodeError, IndexError):
            try:
                data = json.loads(log_text)
            except json.JSONDecodeError:
                return None, None, None
        u = data.get('usage') or {}
        tin = sum(int(u.get(k) or 0) for k in ('input_tokens', 'cache_read_input_tokens', 'cache_creation_input_tokens'))
        tout = int(u.get('output_tokens') or 0)
        cost = data.get('total_cost_usd')
        return (tin or None), (tout or None), (float(cost) if cost is not None else None)
    tin = tout = 0
    for line in log_text.splitlines():
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(ev, dict) and ev.get('type') == 'turn.completed':
            u = ev.get('usage') or {}
            tin += int(u.get('input_tokens') or 0)
            tout += int(u.get('output_tokens') or 0)
    return (tin or None), (tout or None), None


def transcript_path(agent, session):
    """Where the engine keeps the session's transcript (Claude Code: <config>/projects/*/<id>.jsonl; Codex:
    <home>/sessions/**/rollout-*-<thread>.jsonl), or None when it can't be found."""
    import os
    from pathlib import Path
    if not session:
        return None
    if agent == 'claude':
        root = Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home() / '.claude') / 'projects'
        hits = list(root.glob(f'*/{session}.jsonl')) if root.exists() else []
    else:
        root = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex') / 'sessions'
        hits = list(root.glob(f'**/*{session}*.jsonl')) if root.exists() else []
    return hits[0] if hits else None


def link_transcript(agent, session, run_dir):
    """A transcript.jsonl link in the run's folder, so a new session can read what this one did."""
    src = transcript_path(agent, session)
    if not src:
        return None
    link = run_dir / 'transcript.jsonl'
    if link.is_symlink() or link.exists():
        link.unlink()
    link.symlink_to(src)
    return str(src)


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
