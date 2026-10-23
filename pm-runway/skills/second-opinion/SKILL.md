---
name: second-opinion
description: "Two fresh readers, Sol (Codex, through Ringer when it is installed) and Opus, read a design doc as its builders or review a finished branch, so no plan or merge rests on the model that wrote it approving its own work. Use from brainstorming's builder check, from finishing-a-development-branch, when the repo's CLAUDE.md asks for a cross-model review, or when the user says \"second opinion\", \"get Sol on this\" or \"cross-review\"."
---

# Second opinion

Two fresh readers, one from another vendor, at the two points where a second pair
of eyes pays: before a design becomes a plan, and before a branch merges. Not
per task, not per green test run. The plan's own tests and Superpowers' own
reviewers stay the continuous layer; this is the different-vendor check on top.

## The readers

Both get the same packet and run at the same time; neither sees the other's
answer.

- **Sol,** the other vendor: Codex, model `gpt-5.6-sol` at medium effort.
  pm-runway: Ringer is optional. With Ringer installed, use one Ringer task
  (engine `codex`; the `ringer` skill owns spec, check and watch surface).
  Without it, run Codex directly and read-only, with the packet as the prompt:
  `codex exec --sandbox read-only -m gpt-5.6-sol "<packet>"` from the repo root.
  If `codex` isn't installed or signed in on this machine, or this is a cloud
  session without it, say Sol isn't reachable and continue with Opus alone
  (below).
- **Opus,** the same vendor with none of this session's context: a fresh
  subagent on `claude-opus-5` (or Ringer's Claude seat when the work is already
  going through Ringer). Fresh is the point: it hasn't watched the design or the
  code get written.

The packet is read-only context and the question, nothing else: no transcript,
no unrelated history. Merge the two answers before acting: a point both raise
counts once, and a point only one raises is still a point.

## Design mode

Called from brainstorming's builder check, for a project-sized design doc.

- **Packet:** the design doc's path, the repo path, and the instruction to read
  it as the person who will build it and list what they would still need to ask.
- **Check:** every question has a same-line reason; each reader also flags any
  decision it thinks is hard to reverse (`door:`).
- **Back in brainstorming:** sort their questions with the builder check's into
  the same three piles (answered already, minor, theirs). Doors always go to
  the user's pile. One round, together with the builder check's questions.

## Branch mode

Called from finishing-a-development-branch, or when asked, on a finished branch.

- **Packet:** base and head commits, the diff, the design doc and plan the
  branch answers to, `REVIEW.md` if the repo has one, and the test output at the
  head commit. With Ringer, the `cross-review-gate` skill's kit handles the mechanics.
- **Verdict (each reader):** findings with severity and file:line, each tied to the design,
  the plan or `REVIEW.md`; a finding with no reference is noted, not acted on.
  Both also check for a lowered bar: new suppressions, skipped or deleted
  tests, stub implementations, loosened thresholds or check config.
- **After:** fix what it finds in this session (the session keeps its context,
  so it isn't a cold start), rerun the tests, and send the fix once more. A
  second failed review stops: tell the user what's still open and let them
  decide. Never merge past an open finding on your own.

## Unseated

If Sol fails with a quota, auth or model-availability error, or Codex isn't
reachable, retry once, then continue with Opus alone and mark the result
`(Opus only)` where the design doc or the finishing message records it: one
vendor read it, not two. If both fail, or the user says "no second opinion this
time", mark it `(unseated)`. Never present a one-reader or unseated result as a
full second opinion.

## What this replaces

pm's `fast-grill`. Grilling rounds are gone from the default flow; brainstorming
asks the questions and its builder check settles the technical ones. Run
`grilling` by hand when you want to be stress-tested on purpose.
