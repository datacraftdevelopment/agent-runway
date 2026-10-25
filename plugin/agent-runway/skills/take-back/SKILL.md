---
name: take-back
description: "Take over a Runway ticket that got stuck, finish it with the person in this session, and close it out: give it back to Runway, mark it done, or drop it. Use when the person pastes 'Use the runway take-back skill on ticket T-n', or asks to take back, take over, rescue or finish a Runway ticket by hand. Never leaves a ticket taken back."
---

# Take back a Runway ticket

Runway stopped on a ticket (a failed review, a failing check, a question) and the person wants to finish it here.
You work on it together in its own worktree, then end it with exactly one of three commands. **A ticket is never
left taken back:** before this session ends, it is given back, done or dropped.

Use `runway` on PATH, or `/Applications/Runway.app/Contents/Resources/cli/bin/runway`. Run each command on its own
(no `&&`, `||` or `;`: a session with an allow-list refuses chained commands).

## First: is it a question, not a failure?

If the ticket is waiting on a needs-you **question** (Runway asks "Merge PR #41?" or the worker asked which date
format to use) and the person only needs to answer, don't take it back. Answer it, on the person's own words:

```bash
runway go T-17 --note "use ISO dates"
runway no T-17 --note "Mon 26 Oct"
```

## 1. Take it

```bash
runway take T-22
```

It stops the worker if one is running, keeps the branch and worktree, marks the ticket taken back and prints the
worktree path and the branch (`rw/T-22`). Running it again is harmless.

## 2. Read what was tried

```bash
runway show T-22
```

It prints the ticket, its Acceptance lines and every run, each with its record folder,
`~/.runway/runs/<ticket>/<n>/`. Read the last run's folder before changing anything:

- `outcome.json`: what the worker said when it stopped.
- `reviews/code.json` and `reviews/function.json`: both verdicts, with the findings and the failing Acceptance lines.
- `transcript.jsonl`: the session itself, when you need to see what it tried and where it went wrong.

Tell the person in two or three lines what was tried and why it stopped, then agree what to do.

## 3. Fix it, with the person

Work in the worktree `runway take` printed, on its branch. Keep to the ticket and its Acceptance lines. Run the
repo's check (the one in `runway show`) and each Acceptance line's Verify, then commit. Don't push by hand, and never
weaken, skip or delete a test to get green.

## 4. End it with exactly one of these

Before the session ends, say which of the three you're about to run and why, and ask the person. Run it only when
they agree.

```bash
runway give T-22
```

Back to Runway: pushes the commits and queues the ticket. Both fresh reviews (code and function) run again on the new
head, and the gate decides as usual: a low-risk ticket can still merge on its own. The default when the work is
finished but the person wants Runway's reviews.

```bash
runway done T-22 --note "what you checked"
```

Only on the person's own typed go in this session. Pushes the commits, merges the PR if it isn't merged, marks the
ticket done and records the go like `runway go`. It needs a PR (a ticket that never got one is given back instead).

```bash
runway drop T-22 --reason "why"
```

Closes the PR, removes the worktree, and the ticket goes to Done as dropped. For work that turned out not to be
wanted.

All three are safe to run twice. Uncommitted changes stop `give` and `done`: commit them first (or ask whether to
throw them away).

## Never

- End the session with the ticket still taken back.
- Run `done` without the person's typed go, or `drop` without their say-so.
- Merge, close the PR or push by hand: the three commands do it, and Runway records it.
