---
name: stepping-away
description: Session close. Compare this session's Intent to what shipped, write the session entry, note where each plan stands, capture loose ideas, and offer the next session. Use when the user says "stepping away", "wrapping up", "let's close this session out", "starting a fresh session", "I'm done for the day", "let's call it", or similar.
---

# Stepping away

The session close. Capture what happened against the Intent set at the open,
so whoever opens next (later today, tomorrow, someone else) picks up cleanly.
Don't make the user ramble; that's why this skill exists.

An explicit request to close the session authorizes the routine local
close-out: writing the session entry and the files below, then reporting them.
Pushes, client messages and production keep their own permission.

## 1. Gather

- This session's file in `_pm/sessions/`, by the exact path and Session-ID kept
  from the open (never the highest ordinal). Read the Intent and the latest
  re-aim. No session was opened: allocate one now and mark its Intent
  retrospective.
- The plans this session touched: `docs/plans/*.md`, their ledgers under
  `.superpowers/sdd/` when present, and `git log --since=<session start> --oneline`.
- Any design doc written or changed this session (`docs/specs/`).
- The conversation since the last stepping-away.
- Nested sessions this session started: what each finished, what's still running.

## 2. Write the entry

Three sections, leaving the Intent block untouched:

- **Shipped:** tight bullets, files by path, commits linked. Omit if nothing shipped.
- **Tried / Learned / Decided:** narrative, candid about dead ends. Include the
  rulings the plan's ledger recorded that the user should see.
- **Intent vs. outcome:** did we hit done-for-this-session, did we stay in
  scope? If we crossed it, deliberate pivot or unnoticed drift, and why. With a
  re-aim, compare against the latest one and note "original → re-aimed".

## 3. Leave each plan resumable

For each plan in flight, one line under **Open threads**: the plan's path, the
last finished task with its commit, the next task, and anything blocking it.
The ledger is local and gitignored, so this line is what another machine or
another person sees. A design waiting for approval or a go to plan gets a line
too. Something that needs the user goes in its own line, starting `Waiting on you:`.

Nested sessions: never close or stop one that is still working on its lane.
Note it as running, with its name, and leave its ownership alone.

## 4. Capture loose ideas, matching first

Anything that came up and isn't part of a design or plan (a someday idea, an
ask nobody shaped) is offered for `docs/inbox.md`. Match it against the inbox
and the design docs first, by subject: a repeat adds `· re-raised YYYY-MM-DD
<source>` to the existing line, never a second line. A new one is
`- YYYY-MM-DD · <source> · <the idea>`, in client-safe words.

## 5. Only when it applies

- **Client face:** only if `docs/agents/client-face.md` exists. Follow
  [client-face-contract.md](./client-face-contract.md): quote the matching step,
  offer it, record done, skipped or blocked. No file, say nothing.
- **Knowledge log:** only if `knowledge/` changed; append to its `log.md` per
  the `okf` skill.
- **Shared library:** only if something durable surfaced that belongs beyond
  this project and the machine's global instructions name a library for it.
  The bar: if this note vanished, would the next engineer repeat the mistake or
  redo the investigation? If not, write nothing.
- **ADR:** only for a durable choice not already recorded in a design doc.
  `docs/adr/`, in `domain-modeling`'s format.

## 6. Close the record

Write the drafted sections into an entry file, then close by the binding
(`<bound-root>` is the absolute root `whats-next` kept, even if the session
has since moved into a worktree):

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/session.py" --root "<bound-root>" close --session <bound-path> --id <bound-id> --entry-file <entry-text-file>
```

It checks identity, appends the entry and writes `Closed:` last. A repeat
reports `already-closed`. Then offer to commit the session file and any `docs/`
edits; in a team repo, offer to push the branch. Existing permission settles
the offer.

## 7. Sign off and offer the next session

One short summary: what shipped against what was intended (call out drift),
where each plan stands, and the one or two threads the next session should
open on. If ready work remains, offer to start a fresh session for it with a
short prompt: the checkout path, "run `whats-next`", those threads, and this
session's file as the handoff. Several lanes at once is `nested-sessions`, not
this offer. A session that only starts in a fresh worktree won't see
uncommitted work or gitignored files such as `_pm/` and the ledgers: say so.

## What this skill does not do

- Rewrite the Intent to match the outcome. The Intent stays as set.
- Stop, pause or close a nested session or any other running work.
- Fold several sessions into one entry, or reopen a closed session's file.
- Push, message a client or touch production without its own permission.
