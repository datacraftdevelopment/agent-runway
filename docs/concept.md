# Runway Agent: concept

Status: concept, 2026-10-22. Shaped in conversation with Joe the day Runway v1 was retired.

> **Superseded in part, 2026-10-23.** The build is now the `pm-runway` plugin (`docs/specs/2026-10-23-pm-runway-design.md`): Orca replaces Herdr, SSH dispatch and our own app; tickets are files, not rows in a controller database; the loop is a plain script in an Orca tab with a board page; one integration branch per chunk, gated once. The sections below are the earlier thinking and are kept for the record.

## What it is

One board that dispatches coding tickets to agents running on many machines (Mac minis, laptops) and in cloud sessions, and shows what has been dispatched and what is running where.

**Architecture (decided 2026-10-23): one controller, nothing hosted.**

- **Controller:** one always-on Mac (Joe's desktop Mac). It runs the Runway Agent app, holds the board and keeps everything in one local SQLite database: tickets (it is the ticket tracker), claims, receipts, verdicts and decisions. Specs and plans stay in git. See `docs/specs/2026-10-23-controller-database-design.md`.
- **Worker machines** (the other Macs and laptops) are driven from the controller over SSH (Tailscale SSH, so it works wherever a laptop is). Claude Code and Codex run there, inside Herdr so a dropped connection or a closed lid doesn't kill the work. No daemon to install on each worker.
- **Cloud sessions** are started by the controller and report back to its board.
- **The app is the controller's face.** It shows the board (one machine or the whole fleet), starts, stops and pauses dispatch, and answers decisions for any machine. Nothing hides in the background.

**Herdr as the SSH and session layer (checked 2026-10-23, Herdr 0.9.5, Apache-2.0, last commit 2026-10-21).** Each worker runs its own Herdr server; the controller saves each worker once (`herdr machine add <host>`, over normal SSH) and then drives it from scripts with no TUI open: `herdr --machine <label> pane …` / `agent start` / `agent list`, JSON output. Herdr recognises Claude Code and Codex in panes and reports idle, working, blocked, done or unknown, so the app reads agent state from Herdr instead of inventing it. Sessions survive a dropped SSH connection or a closed client; after a machine restart the layout comes back and supported agents can resume, but the original processes don't. Joe can open the Herdr TUI to see every machine's agents in one window and drop into any session. Herdr does not copy config or secrets to workers; sign-ins stay per machine.

Earlier idea, kept for reference: a hosted hub with a daemon on every machine connecting out (AgentConnect's model). Dropped because Joe doesn't need it hosted.

Risks to test first:
- The controller has to be awake for dispatch to run.
- macOS keychain sign-ins (Claude, Codex) are often locked in an SSH session; test on one worker before anything else.
- Sessions must outlive the SSH connection (Herdr handles this).

**Design review 2026-10-23** (Astra and Fable, `docs/review/2026-10-23-panel.md`): only the controller claims; workers write receipts to a local outbox the controller pulls over SSH; Herdr state is advisory; the gate reads risk and policy only from what the controller recorded or the default branch; Ringer is opt-in per ticket, not in review.

## Two kinds of work on the board

- **Steered sessions.** Joe shapes the work by hand (new repo, wayfinder, chunks, specs), talking as much as it needs. These sessions show on the board too, found by the controller rather than reported by a hook (see the controller database design, "Steered sessions").
- **Unattended tickets.** What shaping produces. They run off on whichever machine takes them, get reviewed, and merge on their own only when they are low risk.

## Merge rule

- Risk is set while shaping, default "not low".
- A reviewer (a second model) can raise a ticket's risk, never lower it.
- Tickets touching sensitive paths (auth, payments, migrations, CI) never auto-merge.
- Everything else stops at a PR and becomes a "needs you" card.

## The board

- Every app can show just its own machine or the whole fleet.
- Decisions (yes/no, go/no) can be answered from any app, for any machine. No need to go into a particular machine's app.
- Columns per machine plus cloud is one useful view; status columns (needs you, running, done) is another.

## The skill contract (the part we own)

The daemon is plumbing. The real product is a contract that skills and plugins follow, so pm-sp (and others, such as Matt Pocock's skills) work with it:

1. A skill that files tickets into the hub at the end of shaping, with risk set.
2. ~~A session hook so every session registers itself~~ (2026-10-23: Claude Code desktop doesn't run plugin hooks). The controller finds hand-started sessions itself by scanning each machine's Claude Code session logs over SSH. A hook can still add detail where it runs, but nothing depends on it.
3. Worker skills that claim a ticket, do it, and leave receipts (claimed, blocked, needs you, done, failed).

## Who it's for

**Goal (Joe, 2026-10-23):** something Joe can hand to someone: "load this app, it helps you set up your software factory", so other people use it and give feedback. Open source, likely a public repo, with a simple website pointing to it. No money in it.

That makes these first-class:
- A first-run setup flow: add worker machines, check SSH/Tailscale, check Claude and Codex sign-ins on each, install the skills.
- Nothing tied to Joe's setup: no hardcoded paths or machine names, no dependency on Ringer or other private tools; the skill contract ships with the app (or as a public plugin).
- A permissive licence and docs a stranger can follow.
- Client work never in the repo, issues or examples. The repo is public from day one (Joe, 2026-10-23) to keep that discipline.


Joe first, then a few collaborators. Not a service, and not multi-tenant. Each person runs their own controller. Client work stays on infrastructure its owner controls.

## Existing tools (checked 2026-10-22)

- **AgentConnect** (Apache-2.0, active): daemon per machine, Claude Code via the Agent SDK and Codex, work started from issues, PRs, webhooks or schedules. The best candidate for the hub and daemon. Gaps: agents are placed on a fixed machine, it has no board of its own, and it has no risk-gated merge.
- **DoWorker / Agent Cloud**: closest on paper (board, runner pool), but its BSL licence allows no production use, and it has been quiet since August. Ideas only.
- **BB**: persistent sessions across machines, no ticket queue and no way for a script to start work or read state. Not chosen (2026-10-23); maybe a viewer later.


## Lessons carried from v1 and earlier

- **Loop first.** One real ticket must run end to end before any board polish. Argus died because the loop never ran.
- Keep every rule once, in one protocol. Trackers and stores give facts and writes only.
- A "go" or approval counts only when Joe gives it himself.
- Review is pinned to the exact commit it reviewed.
- Don't use Runway to fix Runway mid-flight.

## Open questions

- ~~UI stack~~ Decided 2026-10-22: one web UI, served locally by the daemon and hosted, in a Tauri desktop shell.
- ~~Ticket store~~ Decided 2026-10-23: the controller's SQLite database is the ticket tracker (replaces the earlier "ticket files in each repo"). No GitHub Issues.
- ~~Herdr or BB~~ Herdr, starting with it (2026-10-23).
- ~~Herdr or tmux~~ Herdr is the SSH and session layer (2026-10-23). AgentConnect is no longer needed.
- Plan terms for subscription logins on always-on daemons.
