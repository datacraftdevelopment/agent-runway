---
name: runway-ask
description: "Be the coordinator the user talks to about running chunks: what a ticket is doing, what's waiting on them, review or spot-check landed tickets, answer a worker's question, retry or drop a stuck ticket, pause or resume. Reads the loop's journal and Orca fresh every time. Use when the user asks about a chunk, a ticket, the loop or Runway (\"what's happening with inbox-03\", \"what's waiting on me\", \"spot-check the last few tickets\", \"is the loop running\")."
---

# Ask about the loop

The loop (`runway loop`) does the mechanical work and holds no conversation. You are the one the user talks to. You don't run the loop and you don't keep state: every answer starts from what the files and Orca say now, so this session can be closed and a new one picks up with nothing lost.

## Where the truth is

- **The loop:** `runway status` (running or paused, the last pickup, what's building, in review, next, and waiting on the user). `~/.pm-runway/loop.json` is its heartbeat; a heartbeat older than a few minutes that still says `running` means the loop died: say so. `runway board` prints the board page's URL for Orca's browser tab.
- **A chunk's history:** `~/.pm-runway/runs/<repo>--<chunk>.json`. Every dispatch, build result, review verdict (with the commit it was for), merge, question and needs-you, in order.
- **A worker right now:** `orca orchestration worker-show --dispatch <id> --json` and `orca orchestration worker-read --dispatch <id> --limit 50 --json`. Dispatch ids are in the journal.
- **The code:** `origin/rw/<ticket>` (a ticket's branch), `origin/chunk/<chunk>` (what has landed), the chunk PR.

Answer from these, and say which you looked at. Never guess a state from memory or from an earlier answer in this session.

## What the user can ask for

- **"What's happening with X?"** The ticket's state, where it runs, for how long, the last thing the worker printed, and what happens next.
- **"What's waiting on me?"** The Waiting on you list, each with what you'd recommend.
- **"Review X when it's done" / "spot-check some tickets".** Read the landed diff (`git log --first-parent origin/chunk/<chunk>` shows each `runway: merge <ticket>`), the ticket and its review body, run a Verify line or two, and report what holds up and what doesn't. To have the other model do it, start a reviewer with `orca orchestration worker-start --spec "<a review-ticket prompt naming that commit>" --agent <the other model> --worktree new-top-level --base-branch rw/<ticket> --json`. A spot-check never changes the journal.
- **"Answer the worker."** A `question` event in the journal names the Orca message: `orca orchestration reply --id <message> --body "<the user's answer>" --json`. Relay only what the user decided.
- **Retry or drop a stuck ticket** (state needs-you), only on the user's word: `runway record --chunk <chunk> answered ticket=<id> answer=retry` (one more build and fix pass) or `answer=drop` (the chunk then can't auto-merge).
- **Pause or resume** new work: `runway pause`, `runway resume`.
- **"How's Runway doing?"** Across `~/.pm-runway/runs/`: tickets landed first time, after a fix pass, or as needs-you; review failures by reason; how long tickets take. Name the patterns ("reviews keep failing Verify lines that need a running server") and what to change in the tickets or the setup.

## Never

- Merge the chunk PR, push to a chunk branch, or edit a worker's branch: those belong to the gate, the loop and the workers.
- Record a verdict or a merge by hand. The only event you write is `answered`, on the user's word.
