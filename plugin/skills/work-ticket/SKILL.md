---
name: work-ticket
description: Work one Runway Agent ticket the controller dispatched to this session, unattended, and report through typed receipts. Use only when a session was started with a dispatch packet (RUNWAY_DISPATCH_ID is set and the prompt names a packet path), or when the user says "work ticket" with a packet. Never for picking up a ticket on your own.
---

# Work a ticket

The controller already claimed this ticket for this session and handed over a packet (JSON: ticket ref, repo, branch, spec and plan paths, Acceptance lines, comments). You build it, open a draft PR, and say how it went in receipts. You never claim, never read the controller's database, never merge.

Below, `R` means `runway-agent receipt --packet <packet path>`.

## 1. Claim check, first

```bash
runway-agent claim-check --packet <packet path>
```

If it fails, stop. Do nothing else and write nothing: this session doesn't hold the claim.

## 2. Workspace

- Clone or fetch the repo under the workspace root (`~/runway-work/<repo name>` unless `docs/agents/worker-env.md` says otherwise), then a fresh worktree on the packet's `branch`. If that branch already exists on origin (a fix pass after review), check it out and build on it.
- `R started --worktree <path>`.
- Read `docs/agents/worker-env.md` (what a fresh worktree lacks, the verify command, paths to leave alone), the spec and the plan named in the packet, and every comment in the packet: a comment from review lists the findings to fix, and an operator's answer to an earlier question is binding.

## 3. Build

- With pm-sp installed: `subagent-driven-development` (or `executing-plans` inline) on the plan tasks this ticket covers. Without it: test first, smallest change, one commit per task.
- Stay inside the ticket. Work the ticket's Acceptance lines; anything else you notice goes in the PR body under "Not done", not in the diff.
- Decisions the plan didn't settle: make them and write each as a ruling in the PR body.
- `R progress --note "<one line>"` at each finished task, so the board isn't blind.

## 4. Verify

Run the repo's check command (from `worker-env.md`, else `runway.json`'s `check_cmd`) fresh, after the last edit. Red and you can't fix it inside the ticket: `R failed --reason "<what failed>" --output "<last 40 lines>"` and stop. The gate runs CI or its own check later; your run is for you, not proof.

## 5. Hand off

- Push the branch. Open a **draft** PR against the default branch whose body says `Refs <ticket ref>` (never "Closes"), the Acceptance lines with how each is met, rulings, and "Not done".
- `R build-done --head <full sha of the pushed head> --pr <number> --model <claude|codex>`.

That's the end of the session. Review and the gate follow on the controller; build done is not ticket done.

## When to stop early

Each ends the session with exactly one closing receipt:

- `R blocked --reason "<the dependency>"`: something outside the ticket must land first.
- `R needs-you --question "<one question>" --recommended "<your answer>" [--option A --option B]`: the ticket or spec is wrong or ambiguous in a way that changes the result. One question, with the answer you'd pick. The controller asks the operator; you never answer your own question.
- `R failed --reason "…"`: anything else that stops you.

## Allowed without asking

The protocol steps: the claim check, writing receipts, the clone and worktree under the workspace root, commits and pushes to the packet's branch, the draft PR. Everything else that leaves the worktree or can't be undone (other branches, deploys, deletes outside the worktree, secrets, installs that change the machine) is a `needs-you`.
