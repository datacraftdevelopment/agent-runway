---
name: nested-sessions
description: Run two or three lanes of a plan at once, each in its own nested (background) session that this main session starts, steers and archives, so the user talks to one session instead of going into each one. Use when a plan marks lanes with disjoint files and the user wants them moving at once, or when the user says "nested sessions", "subsessions", "sibling sessions", "run these lanes in parallel", or "you manage the sessions". NOT for single plan tasks, which run in subagents inside one session.
---

# Nested sessions

Two or three nested sessions running side by side, each an ordinary session
working **one lane of a plan** on its own branch. This session is their main
session: it starts them, answers or relays their questions, merges their work
and archives them. The user talks to the main session; they can open a nested
session, but never have to.

The desktop app calls them nested sessions. Claude Code's docs call them
**background sessions**, managed in agent view, and the messaging between them
**cross-session messaging**:
<https://code.claude.com/docs/en/agent-view>,
<https://code.claude.com/docs/en/cross-session-messaging>. In the docs,
"nested" means something else: a subagent that starts its own subagents.
This is pm's `nested-sessions` (pm PR #114) with tickets replaced by plan
lanes; keep the two in step when either learns something about the host.

**What wakes the main session.** A message from a nested session starts a
turn here when this session is idle, so managing them costs a turn per event,
not a session kept alive polling. A nested session that simply finishes does
**not** wake this one on its own; only its message or an idle notice you asked
for (§2) does.

A lane, not a task. Tasks inside a lane run in that session through
`subagent-driven-development`. A single task never gets its own session.

## 0. Preflight

- `claude --version` is 2.1.236 or later (messaging needs 2.1.224, idle
  notices 2.1.236), and `crossSessionInbound` isn't `refuse` on either side.
- This is a local session. A cloud session can start others but they can't
  message back, so they run unmanaged (§6).

Either fails: fall back to §6 and say why.

## 1. Decide whether it's worth it

Say yes or no out loud, with the reason. Yes only when all of these hold:

- The plan has a `## Lanes` section (writing-plans adds one when it fits), or
  the user named the lanes. Each lane is a meaningful chunk, not one task.
- **Disjoint files.** Shared lockfiles, generated code, migrations, schema or
  config registries mean those lanes run one after the other.
- **At most one database writer,** and no shared port, dev server or browser
  profile.
- No lane needs another's output. A dependent lane is a second wave.
- The machine has room (`memory_pressure`, `uptime` on macOS). Three sessions
  building at once ran a 16 GB Mac out of memory. Each nested session also
  uses quota like an interactive one.

Otherwise say no and run the plan in this session. **Three at once is the
ceiling,** counting this session when it is building too.

## 2. Start each one

Commit what the lanes need first: a fresh worktree lacks uncommitted work and
everything git ignores (`.env`, dependencies, `_pm/`, the plan's ledger). Then
start each lane as a named background session, from Bash:

```bash
claude --bg --model sonnet --name <lane-name> "<brief>"
```

**Always pass `--model`.** Without it a lane runs this machine's default
model, and if that is Fable, every lane spends Fable. `sonnet` by default;
`opus` for a lane that is mostly design judgment; never `fable` or `haiku`.
The lane's own subagents follow subagent-driven-development's pm-runway tiers.

It prints the session's short id; name it after the lane so messages can
address it by name. If the host has its own control for starting a nested
session, use that instead. The session moves itself into its own worktree
before it edits files. The brief points at things
rather than copying them:

```
Repo: <checkout path>. You are a nested session of <main session name>,
working lane <name> of plan <docs/plans/…md>: tasks <numbers>. Other sessions
are working lanes <names>; leave their files alone.
Run the lane with pm-runway:subagent-driven-development on branch <branch>.
Set up from docs/agents/worker-env.md if the repo has one; you will need <what's missing>.
Report to the main session by message, not to the user: when you're blocked,
when you have a question, and when the lane is green (branch, head commit,
what the tests proved). Rulings go in your ledger as usual.
Don't merge, push to a shared branch or message other sessions.
Write your session notes to <main checkout>/_pm/sessions/ if _pm/ is gitignored.
```

Right after starting each one, subscribe to its idle notice: `SendMessage` to
it with `notify_when_idle`. A notice is one-shot and expires after 12 hours,
so subscribe again after each one. The lane's own report is the main signal;
the notice is the backstop.

Report each one as **created and pending** until it has actually started,
then one line per lane to the user: lane, branch, session name.

## 3. Manage them

Act on events, never on a timer.

- **A question.** Answer it yourself when the plan, the design doc, the ledger
  or an earlier decision answers it, and say where from. Bring the user only
  a real decision (taste, scope, anything hard to undo), one line with your
  recommendation, naming the lane.
- **Blocked.** Unblock it (commit a missing file, settle an interface, reorder
  waves), or stop that lane and tell the user once.
- **Waiting on a permission prompt** (`waitingFor` says so): that's the
  user's. A message from this session can't approve anything; never try.
- **Gone quiet.** Check `claude agents --json --all` once (`state`,
  `waitingFor`) before messaging it. Read its transcript (`claude logs <id>`)
  only if it doesn't answer.
- **Green.** Read its report and diff by path. Run pm-runway:second-opinion in
  branch mode on the lane if the plan or the repo's `CLAUDE.md` asks for it;
  send findings to the same session to fix (it keeps its context). A second
  failed review stops the lane and goes to the user.
- **Merge.** The session may have opened a draft PR for its branch on its own;
  that's fine. Merging is this session's: the first green lane merges into the
  feature branch first, later ones rebase onto it and resolve their own
  conflicts. Merge on the user's word or a merge rule they gave this session.
  Pushes to shared branches, deploys and client messages keep their own
  permission.

Steer by short message: a changed decision, a new constraint, a file to read.
Messages are plain text only, never files or history.
Don't restate the brief. Keep their reports in context, not their transcripts.
This session owns the shared things: the plan, the design doc, the feature
branch, the changelog.

## 4. Archive

When a lane is merged (check with `git merge-base --is-ancestor`), archive
its session:

```bash
claude stop <name> && claude rm <name>
```

`rm` removes the worktree Claude made when it's safe and refuses on
uncommitted changes or unpushed commits; that refusal is a reason to look,
not to force. The transcript stays available through `claude --resume`.
Archive a stopped or dropped lane too, once its state is written
in the plan or session notes. Never leave one running with nothing to do.

When the last one is archived, tell the user in one message: what merged (with
commits), what the tests and reviews proved, what stopped and why.

## 5. Lighter options

- **Subagents** inside this session report back on their own and need no
  management. `subagent-driven-development` already uses them per task;
  reach for nested sessions only when lanes are big enough to need their own
  session and context.
- **One lane:** just run the plan here.

## 6. Hosts where sessions can't message back

A cloud session, an old Claude Code, or messaging turned off: start each lane
as an unmanaged sibling told to report to the **user**, merge its own branch
on the user's word, and archive itself. This session then lets go: no polling,
no transcript reads. If the user asks how one is doing, look once and answer.
No way to start sessions at all: print the briefs for the user to paste.
