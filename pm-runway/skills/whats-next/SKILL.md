---
name: whats-next
description: Session open. Read where the work stands (design docs, plans and their ledgers, recent sessions), propose one or two things to pick up, and write this session's Intent. Use when the user says "what's next?", "what should I work on?", "where did we leave off?", "catch me up", or starts a session cold without a named task.
---

# What's next

The session open. Read first, then propose. Don't ask "what do you want to
work on?": that's what the user is asking you.

**If the user already named the work, there's no pick to make.** Read just
enough to write the Intent for it, write it, and start.

## 1. Read

The shared record first, the personal log second (`WORKFLOW.md`: `docs/` is
truth, `_pm/` is log).

First bring the record up to date: if the branch has an upstream and the
working tree is clean, `git pull --ff-only`, so a wayfinder map or plan moved
forward on another computer shows here. If the pull can't fast-forward, say so
and read what's local.

- **Plans in flight.** `docs/plans/*.md`, newest first. For each, find how far
  it got: its ledger at `.superpowers/sdd/<plan-name>/progress.md` when this
  checkout has one (it's gitignored, so another machine or worktree won't), and
  `git log` for the commits its tasks name. A plan with tasks left is a stream
  of work; the first unfinished task is its pick-up.
- **Designs without a plan.** `docs/specs/*.md` with no plan pointing at them:
  approved designs waiting for a go to plan, or drafts waiting for approval.
- **Shipped records.** `docs/shipped/` tells you which designs were delivered
  (`ship-acceptance`); a `released-with-exceptions` record stays visible until
  the user accepts its open tail.
- **Waiting on the user.** Open questions in a design doc, rulings in a ledger
  marked as needing the user, a second-opinion finding left open.
- **The inbox,** `docs/inbox.md` if the repo keeps one: loose ideas, one line
  each. A line is a brainstorming candidate, not a task. Never a gate on
  starting work.
- `docs/adr/` newest entries and `GLOSSARY.md` if present.
- `_pm/skeleton.md`, the project's macro why.
- The last one to three files in `_pm/sessions/`, most recent first, especially
  their open threads and Intent vs. outcome.
- A wayfinder map, if the repo has one (`wayfinder`): its frontier is
  decision work, not build work. Tickets carrying a `Waiting on:` line go
  under *Waiting on you*. A cleared map's chunks are brainstorm candidates,
  in the order it set.

## 2. Propose

Keep work the session can take and decisions only the user can make apart.

```
Where we are: <one sentence: which designs and plans exist, how far each got>.
Ready to pick up: <first unfinished task of a plan, an approved design to plan, or "nothing in flight">.
Waiting on you: <a design to approve, a go to plan, open questions, or "nothing">.
Recommended: <one pick-up> because <reason from what you read>.
Also worth: <maybe one more>.
Watch-outs: <a plan with no commits in a while, a ledger and git that disagree, an unseated review>.
```

New work with no design yet goes to `brainstorming`. Work that is genuinely
foggy, with several unknowns that depend on each other, starts with
wayfinder, which runs only when the user names it: recommend it, don't
start it; its destination is a set of chunks, a brainstorm each.

## 3. Write the Intent

Two or three sentences of plain prose: what this session pushes on, why it
matters, what done-for-this-session looks like, what's out of scope. Scope it
to one session. Once the pick is settled (a named task counts), open the
session record:

```bash
ROOT="$(git rev-parse --show-toplevel)"
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session.py" --root "$ROOT" open --name <handle> --intent '<session intent>'
```

Keep the absolute `ROOT` with the returned `path` and `id` (pm-runway): the plan
may move this session into a worktree, and close and re-aim must still find
the same file. Keep all three in this conversation and in any handoff
summary; they bind this conversation to this session. Never pick a session file
by its ordinal. On resume, reread that file's Intent and latest re-aim.

## 4. Work

The default is this session, with the user in the loop: brainstorming, then
the plan, then running it (`subagent-driven-development` or
`executing-plans`), then `finishing-a-development-branch`. When a plan has
lanes and the user wants them moving at once, `nested-sessions` runs them
side by side from this session.

## No history yet

A brand-new project: offer to draft the skeleton if it is still a placeholder,
or to brainstorm the first piece of work. The Intent is then "draft the
skeleton" or "design the first piece".
