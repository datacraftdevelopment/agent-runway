# pm-runway: one plugin, tickets as files, Orca as the runner

Status: agreed in conversation with Joe on 2026-10-23, in the project's prior-art thread and its build thread. Built on branch `claude/project-thread-4tbxvb`.

## Decisions

- **One plugin, `pm-runway`,** for the whole workflow: pm-sp's session and shaping layer, our own versions of Matt Pocock's to-spec, to-tickets and implement-spec (plus his tdd and code-review), and Runway. Someone installs one plugin. pm-sp stays in the marketplace; a machine installs one or the other.
- **Matt Pocock's way of working** is the spine: wayfinder for foggy work, a spec in his to-spec shape plus our Acceptance lines, his tracer-bullet tickets, his implement-spec pattern spread across machines.
- **No separate plan document for ticketed work.** The spec and the tickets are the plan; each worker plans its ticket inside its own session.
- **One integration branch per chunk** (`chunk/<chunk>`). Tickets land there after review; the gate runs once, on the chunk PR to main.
- **Orca is the runner** (stablyai/orca, MIT). Workers start with `orca orchestration worker-start`, on paired Macs with `--on`. It uses the person's own Claude Code and Codex CLI sign-ins on each Mac.
- **The loop is a plain script,** not an agent: `runway loop` in an Orca terminal tab redraws a status screen each tick, writes a board page for Orca's browser tab, and can be paused. Every judgment (build, review, fix, whole-chunk review) is a fresh short Orca worker, so no coordinator's context grows.
- **A coordinator to talk to,** `runway-ask`, reads the journal and Orca fresh each time: "what's happening with X", "review it when it's done", spot-checks.
- **Tickets are files** in `docs/maps/<effort>/tickets/`. Run state lives in Orca and in a per-chunk JSON journal on the controller. No SQLite store.
- **Everything in Orca, no separate app.** An installer app may come later.
- **Ringer is optional.**

## Acceptance

- [ ] A1: On a fresh Mac, following `SETUP-AGENT.md` ends with `setup/doctor.sh` (and `--controller` on the controller) passing. Verify: run it on both Macs of the first test.
- [ ] A2: The practice chunk (`setup/practice/`, three tickets) runs from `runway start` to merged on main with nobody touching it: practice-01 and practice-03 build at the same time on two different Macs, each reviewed by the other model, then practice-02, then the whole-chunk review and the gate. Verify: the board and `runway status` during the run; `git log --first-parent main` after.
- [ ] A3: A raised risk or a failing check stops the chunk at the gate with the reasons on the board, and nothing reaches main. Verify: a second run of the practice chunk with one ticket marked `not-low`.
- [ ] A4: `runway-ask` answers "what's happening with practice-02?" and "what's waiting on me?" from a fresh session, matching the board. Verify: ask it during the A2 run.

## Not proven

Orca's JSON receipts, reading a run's inbox from a plain terminal, and `--on` with `--repo` on a paired Mac were read from Orca's source, not yet run. A2 is the test.
