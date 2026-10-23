---
name: review-ticket
description: Review a Runway Agent ticket's head commit on the model that did not build it, and record the verdict pinned to that commit; or explain how the review seat and the merge gate decide. Use when the controller runs a review, when the user says "review DEMO-4", "run the review seat", "why didn't this merge", or asks what the gate checks.
---

# Review a ticket

The controller owns review. A builder's `build-done` receipt names the head and the PR; the controller then runs the other model on that exact commit, records the verdict, and runs the gate.

## Run it

```bash
runway-agent review run DEMO-4
```

It checks out the head in a throwaway worktree on the controller, picks the seat (Codex if Claude built it, Claude if Codex did), calls it directly (`codex exec --sandbox read-only` or `claude -p` in plan mode) with `templates/review-prompt.md`, and records the verdict. The prompt is self-contained, so a seat without this plugin installed reviews the same way. Which models a fleet has: `"models"` in `~/.runway-agent/config.json` (default both).

## If you are the seat

Follow the prompt you were given. Read the diff against the ticket's Acceptance lines and the repo's `REVIEW.md`, change nothing, and end with the one JSON line it asks for. Raise risk to `not-low` when the change touches auth, payments, migrations, CI, deletes, credentials or a public interface, or goes past the ticket's scope. Unreadable output counts as `needs-you`, never `pass`.

## Recording a verdict by hand

When a person reviewed it:

```bash
runway-agent review record DEMO-4 --verdict pass --commit <40-char sha> --model human
```

## The rules (enforced in code)

- A verdict is pinned to a full commit sha. A new push after review means a new review.
- `fix` sends the ticket back for one fix pass with the findings as a comment. A second `fix` becomes `needs-you`.
- A reviewer can raise risk, never lower it.
- With one model in the fleet, review runs on that model and its best verdict is `needs-you`.

## What the gate checks

`runway-agent gate DEMO-4` (`--dry-run` to see without acting) merges only when all hold, else it opens a needs-you card:

1. Risk is `low` in the controller's store (set at filing, never lowered).
2. The latest review is `pass`, on the PR's current head, from the other model.
3. Checks are green: CI on the head, or, with no CI, the gate runs `check_cmd` itself on the head. Pasted output never counts.
4. No changed path is sensitive: the defaults (auth, payments, migrations, CI, `runway.json`) plus `sensitive_paths` from `runway.json` as the default branch has it.

Then it marks the PR ready and merges with `--match-head-commit`, so a push in between makes the merge fail instead of landing unreviewed code. An operator's `runway-agent answer <id> merge --by <name>` on a gate card merges only the head the card showed.

Ringer isn't part of review. It belongs only to tickets filed with `Strategy: swarm`, which v1 doesn't run.
