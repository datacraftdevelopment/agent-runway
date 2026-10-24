# Plan: Runway app

Design: `docs/specs/2026-10-23-runway-app-design.md`. Mock: https://claude.ai/artifact/MzYxCva9uyogGxmEKFFNJ3.
Joe's order (2026-10-23): the look first, then the plumbing. The loop is known to work from v1 and the Orca branch.

## Where each part is built

- **The app** (Swift) builds only on a Mac. Those tasks run in a session on Joe's Mac (Remote Control or Claude Code
  there), not in a cloud container.
- **The `runway` command, the database and the skills** (Python, stdlib only, and Markdown) build and test anywhere.
- One branch per phase off `main`, one draft PR each. A task is one commit.

## Phase 0: three spikes (half a day, nothing kept but notes)

Answer the risks before building on them. Each writes its finding into `docs/quirks.md`.

- [x] **S1. SwiftUI without Xcode.** On Joe's main Mac (Command Line Tools only), `swift build` a tiny `MenuBarExtra`
  app plus one window, and open it. If it fails, the fallback is installing Xcode (free) and saying so in setup.
- [ ] **S2. Sign-ins over SSH.** From the main Mac, `ssh <second Mac> 'claude -p "say ok"'` and
  `ssh <second Mac> 'codex exec "say ok"'`, both non-interactive. If the keychain is locked, find the fix
  (`security unlock-keychain`, a token file, or `claude setup-token`) and note what setup must do.
- [ ] **S3. Cloud runs from a terminal.** Find and try the commands that start a Claude Code web session and a Codex
  cloud task on a repo with a prompt, and how to learn when each finished (the PR is the fallback signal).

## Phase 1: the app on sample data (the look, clickable)

Goal: Joe runs the app on his Mac and it looks and clicks like the mock, fed by a sample `status.json`.

Source: Runway v1's SwiftUI app (archived private `runway` repo, `factory/app/`). Copy views selectively into this
public repo; review every copied file for personal names, paths and client names before committing. Leave out
Sparkle (updates), Ringside, rounds and Linear-era code. SwiftTerm stays out for now ("Open session" opens Terminal).

- [x] 1.1 Swift package at `app/`: `RunwayCore` (models, parsing, no UI) and `Runway` (the app). `make-app.sh` wraps
  it into `Runway.app`. Check: `swift build`, `swift test`.
- [x] 1.2 Models in `RunwayCore`: Repo (main computer, runs on), Runner (kind: this Mac, SSH Mac, cloud; slots;
  state), Agent (Claude Code, Codex; available or resting until), Ticket (column, agent, risk, runs on, stage,
  PR, review, question). Decoded from `runway status --json` shape; fixture `sample-status.json` matches the mock.
  Check: unit tests over the fixture.
- [x] 1.3 Shared look: colours and chips (Claude clay, Codex blue, Any grey; risk low green, not low pink), stage bar
  with Build, Check, Review, Merge labels. Check: SwiftUI previews.
- [x] 1.4 Main window: sidebar (repos with status and main computer; where tickets run with load; agent states),
  toolbar (status pill, Runs on menu, Board/Activity, Pause), Board (four columns, no drag and drop), inspector
  (fields, Runs on menu, Needs-you box with Go/No and a note, Open session). Activity tab. From v1's
  `RunwayWindow`/`BoardView`. Check: run the app on the sample.
- [x] 1.5 Side panel (keep on top): Needs you, a card per repo with Start/Stop and what runs where with agent colour,
  agent states. From v1's `SidePanel`. Check: run it.
- [x] 1.6 Menu bar: icon with a needs-you count; Needs you, repos, pause for an hour, open panel/window, quit.
  From v1's `RunwayBarApp`. Check: run it.
- [x] 1.7 First run screen: the three steps and the live "what setup has found" table (from sample data for now).
  From v1's `SetupSheetView`. Check: run it.
- [ ] 1.8 Joe clicks through it on his Mac. Changes he asks for land here, before Phase 2.

## Phase 2: the database and the `runway` command

- [x] 2.1 `runway/` Python package, stdlib only, `bin/runway`. SQLite schema at `~/.runway/runway.db`: repos,
  runners, agents, tickets, blockers, runs (attempts), reviews, answers, events. Migrations by version number.
  Reuse `store.py` from PR #2 where it fits. Check: unit tests on a temp database.
- [x] 2.2 `runway file` (from stdin JSON or a Markdown file; validates risk reasons, blockers, runs-on) and
  `runway import` (reads `runway/tickets` branch files from cloud sessions, idempotent). Check: tests.
- [x] 2.3 `runway status --json` in the shape the app's fixture already uses (the fixture becomes a test).
- [x] 2.4 `runway go|no <ticket> [--note]`, `pause|resume [repo|runner] [--for 1h]`, `runs-on <repo|ticket> <runner|any|main>`.
- [x] 2.5 The app reads `runway status --json` (polls every few seconds) and its buttons call these commands.
  Check: file a ticket in a terminal, see it appear in the app.

## Phase 3: the skills (Claude Code and Codex)

- [ ] 3.1 Plugin layout that installs into both Claude Code and Codex (one skill text, two manifests), no Ringer.
- [ ] 3.2 `file-tickets`: proposes the batch table (risk with reason, agent, waits on, runs on), files on the typed
  go with `runway file`; over SSH from a non-Runway Mac; to the `runway/tickets` branch from a cloud session.
- [ ] 3.3 `setup`: checks tools and sign-ins, adds this computer as a runner, picks repos and their main computer;
  `join` adds another Mac from that Mac; cloud connect. Writes results to the database (the first-run table).
- [ ] 3.4 `work-ticket` and `review-ticket` (from PR #2, trimmed): worktree, draft PR, outcome file; review pinned to
  the head commit, may raise risk only.
- [ ] 3.5 `runway` skill: status, what needs me, go/no on the person's own words, pause/resume.
- [ ] 3.6 The app's first run installs the command and the skills, then opens Claude Code or Codex on setup.

## Phase 4: the loop across runners

- [x] 4.1 `runway loop` (started by the app as a child process; stops dispatching when the app quits): each tick
  imports cloud tickets, picks ready tickets, respects runs-on and slots, starts runs, reads outcomes.
- [x] 4.2 This Mac runner: worktree + tmux + `claude -p` / `codex exec`, outcome file. Check: one practice ticket.
- [ ] 4.3 SSH Mac runner: the same over `ssh`, using S2's finding. Check: one ticket on the second Mac.
- [ ] 4.4 Cloud runner: using S3's finding. Check: one ticket in the cloud.
- [x] 4.5 Review by the other agent, then the gate (from PR #3's `gate.py`): low risk + review pass on head + checks
  green + no sensitive path, else needs-you.
- [x] 4.6 Usage-limit failover (from PR #3's limits): requeue without spending the fix pass; agent rests until reset.
- [ ] 4.7 Run the design's Acceptance A1 to A5 on a practice repo across this Mac, a second Mac and cloud; record the
  result with `ship-acceptance`.

## Not in this plan

Auto-update, code signing and notarisation (since moved in: `docs/specs/2026-10-24-app-updates-design.md`), a website, Windows or Linux, an in-app terminal.
