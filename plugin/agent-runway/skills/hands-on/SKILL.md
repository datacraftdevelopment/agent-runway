---
name: hands-on
description: "Build work in this session with the person: hands-on tickets Runway can't prove on its own (a real device or camera, or the person's eye on how it looks and feels), or a whole spec built here because the repo isn't in Runway or the spec says runway: no. Plan, build test-first, have the person check what only they can, and close it. Use when the person says 'do the hands-on tickets', 'build it here', or file-tickets has just filed hands-on tickets."
---

# Do the hands-on tickets

file-tickets sorts shaped work into two kinds of ticket. Runway tickets run on their own. **Hands-on** tickets need
something an unattended agent can't supply: a real device or camera, or the person judging how it looks and feels.
Runway never starts those; they wait on the board, and some Runway tickets may wait on them. This skill does them
here, with the person, and closes each one so the work waiting on it can start.

Use `runway` on PATH, or `/Applications/Runway.app/Contents/Resources/cli/bin/runway`. Run each command on its own
(no `&&`, `||` or `;`: a session with an allow-list refuses chained commands).

## No tickets: building a spec here

In a repo that isn't in Runway (`runway repo which` doesn't print its name), or when the spec says `runway: no`,
there are no tickets and no `runway` commands. The spec is the work: build it on a branch of this checkout (or a git
worktree), following steps 3 and 4 below, then finish the branch the repo's usual way (a PR or a merge, on the
person's go). Skip steps 1, 2 and 5.

## 1. See what's yours

```bash
runway hands-on
```

It lists each hands-on ticket with what waits on it. Agree the order with the person: the ones Runway tickets wait on
come first. Then, for the first one:

```bash
runway show T-4
```

Read its Acceptance lines and the spec it points at before changing anything.

## 2. Take it

```bash
runway take T-4
```

It prints a worktree and a branch (`rw/T-4`). The ticket stays the person's, in Up next; nothing is stopped. Work in
that worktree (it opens in Xcode or any editor like any other folder). If two or three hands-on tickets share their
code, take each and say which worktree holds which.

## 3. Build it

- **More than a step or two:** write a short plan with `agent-runway:writing-plans` (in `docs/plans/`), pointing at
  the spec rather than restating it. Run it with `agent-runway:subagent-driven-development` when this session can
  start subagents, or `agent-runway:executing-plans` when it can't (or the person wants it done inline).
- **Every change test-first:** `agent-runway:test-driven-development`. A bug: `agent-runway:systematic-debugging`,
  reproduce before fixing.
- Commit in the worktree as you go. Don't push or merge by hand: `runway done` does it.

## 4. The part only the person can check

For each Acceptance line that needs the device or their eye, tell the person exactly what to do and what to look for
("install the build on the phone, open Log, point the camera at the floor: the preview fills the frame"), then wait
for their answer. Run the repo's check and every line you can check yourself, following
`agent-runway:verification-before-completion`: the command, its output, then the claim.

Never mark a line checked that the person didn't confirm. If a line fails, fix it and ask again.

## 5. Close it, on the person's go

Commit everything in the worktree, then say what you're about to run and why, and ask. Only on their typed go:

```bash
runway done T-4 --note "preview fills the frame on the phone"
```

Runway runs the repo's check on the commits, pushes the branch, opens the PR and records the person's go as the
function review of that commit. A fresh code review and the usual gate still run, so nothing reaches the base branch
unreviewed. Most hands-on tickets aren't low risk, so the gate will ask the person to merge once more after the code
review passes: tell them that second ask is coming. The note goes on the record: say what was checked, in the
person's words.

**No code change at all** (a check on a device, a look at how something feels):

```bash
runway done T-4 --no-code --note "checked the colours on the phone in daylight"
```

`runway done` refuses anything in between: work with no worktree, or commits already merged into the base branch by
hand. Never merge hands-on code yourself; it would skip the review.

If the code review fails, the ticket comes back to Up next as hands-on with the findings. Take it again, fix them, and
run `runway done` again on a new go: it reuses the PR.

The Runway tickets waiting on it start once it merges (or closes). Then go on to the next hands-on ticket.

## Not wanted after all

```bash
runway drop T-4 --reason "why"
```

Only on the person's say-so. Tickets that waited on it are released.

## Never

- Run `runway done` without the person's typed go, or claim an Acceptance line they didn't check.
- Push, merge or close the PR by hand, or merge the work into the base branch yourself: `runway done` and the gate do
  it, and Runway records it.
- Use `--no-code` for a ticket that changed code.
- Leave uncommitted work in a worktree at the end of the session.
