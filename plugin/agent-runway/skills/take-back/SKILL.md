---
name: take-back
description: "Work on a Runway ticket with the person in this session: read it and its last run, talk it through, take it back only if code is going to change, and always end by telling Runway what happened (answer it, give it back, mark it done, drop it, or leave a note). Use when the person pastes 'Use the runway take-back skill on ticket T-n', or asks to look at, take back, take over, rescue or finish a Runway ticket. Never leaves a ticket taken back."
---

# Work on a Runway ticket

The person copied this ticket's prompt from Runway ("Work on this in Claude Code or Codex"). Start by reading and
talking, not by claiming it: most of the time they want to understand it, answer it or nudge it. Take it back only
when you're about to change code. **Whatever happens, end by telling Runway**, so the board matches what happened
here.

Use `runway` on PATH, or `/Applications/Runway.app/Contents/Resources/cli/bin/runway`. Run each command on its own
(no `&&`, `||` or `;`: a session with an allow-list refuses chained commands).

## 1. Read it

```bash
runway show T-22
```

It prints the ticket, its state, its Acceptance lines and every run, each with its record folder
`~/.runway/runs/<ticket>/<n>/`. Read the last run's folder:

- `outcome.json`: what the worker said when it stopped.
- `reviews/code.json` and `reviews/function.json`: both verdicts, with the findings and the failing Acceptance lines.
- `transcript.jsonl`: the session itself, when you need to see what it tried and where it went wrong.

## 2. Talk it through

Tell the person in two or three lines where it is, what was tried and why it stopped. Then agree what to do. Most
often it's one of these:

- **Just an answer.** It waits on a question ("Merge PR #41?", or the worker asked which date format to use). Answer
  it in the person's own words, and don't take it back:

  ```bash
  runway go T-17 --note "use ISO dates"
  runway no T-17 --note "Mon 26 Oct"
  ```

- **Only talking.** You looked, nothing changes yet. Leave what you found on the ticket, then stop:

  ```bash
  runway note T-22 "Checked: the API key is missing on the runner. Wait for it."
  ```

- **Code needs to change.** Go on to step 3.

## 3. Take it, then fix it with the person

```bash
runway take T-22
```

It stops the worker if one is running (so Runway and you aren't both working on it), keeps the branch, marks the
ticket taken back and prints the worktree path and the branch (`rw/T-22`). Running it again is harmless.

Work **in that worktree**, on its branch, not in the person's main clone. The board shows how long it's been taken
back and when the worktree last changed, so commit as you go. Keep to the ticket and its Acceptance lines. Run the
repo's check (the one in `runway show`) and each Acceptance line's Verify, then commit. Don't push by hand, and never
weaken, skip or delete a test to get green.

## 4. End it by telling Runway

Before the session ends, say which of these you're about to run and why, and ask the person. Run it only when they
agree.

```bash
runway done T-22 --note "what you checked"
```

Only on the person's own typed go. Pushes the commits, merges the PR if it isn't merged, marks the ticket done. Use
it when you finished the work here and checked every Acceptance line yourself: giving it back would have Runway build
again work that's already done. It needs a PR (a ticket that never got one is given back instead).

```bash
runway give T-22
```

Back to Runway: pushes the commits and queues the ticket. Runway's worker carries on from your commits and both fresh
reviews run on the new head; a low-risk ticket can still merge on its own. Use it when Runway should finish or review
the rest.

```bash
runway drop T-22 --reason "why"
```

Closes the PR, removes the worktree, and the ticket goes to Done as dropped. For work that turned out not to be
wanted.

All three are safe to run twice. Uncommitted changes stop `give` and `done`: commit them first (or ask whether to
throw them away). If you only talked (step 2), the `runway go`, `runway no` or `runway note` you ran is the ending.

## Never

- End the session with the ticket still taken back, or with nothing told to Runway.
- Take it back just to look at it.
- Run `done` without the person's typed go, or `drop` without their say-so.
- Merge, close the PR or push by hand: the commands do it, and Runway records it.
