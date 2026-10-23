# Runway Agent: concept

Status: concept, 2026-10-22. Nothing built yet. Shaped in conversation with Joe the day Runway v1 was retired.

## What it is

One board that dispatches coding tickets to agents running on many machines (Mac minis, laptops) and in cloud sessions, and shows what has been dispatched and what is running where.

**Architecture (decided 2026-10-23): one controller, nothing hosted.**

- **Controller:** one always-on Mac (Joe's desktop Mac). It runs the Runway Agent app, holds the tickets and the board, and is the only place state lives.
- **Worker machines** (the other Macs and laptops) are driven from the controller over SSH (Tailscale SSH, so it works wherever a laptop is). Claude Code and Codex run there, inside tmux or Herdr so a dropped connection or a closed lid doesn't kill the work. No daemon to install on each worker.
- **Cloud sessions** are started by the controller and report back to its board.
- **The app is the controller's face.** It shows the board (one machine or the whole fleet), starts, stops and pauses dispatch, and answers decisions for any machine. Nothing hides in the background.

Earlier idea, kept for reference: a hosted hub with a daemon on every machine connecting out (AgentConnect's model). Dropped because Joe doesn't need it hosted.

Risks to test first:
- The controller has to be awake for dispatch to run.
- macOS keychain sign-ins (Claude, Codex) are often locked in an SSH session; test on one worker before anything else.
- Sessions must outlive the SSH connection (tmux or Herdr).

## Two kinds of work on the board

- **Steered sessions.** Joe shapes the work by hand (new repo, wayfinder, chunks, specs), talking as much as it needs. These sessions show on the board too.
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
2. A session hook so every session, including ones started by hand, registers itself and reports status.
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
- **BB**: persistent sessions across machines, no ticket queue. A possible session viewer.


## Lessons carried from v1 and earlier

- **Loop first.** One real ticket must run end to end before any board polish. Argus died because the loop never ran.
- Keep every rule once, in one protocol. Trackers and stores give facts and writes only.
- A "go" or approval counts only when Joe gives it himself.
- Review is pinned to the exact commit it reviewed.
- Don't use Runway to fix Runway mid-flight.

## Open questions

- ~~UI stack~~ Decided 2026-10-22: one web UI, served locally by the daemon and hosted, in a Tauri desktop shell.
- Ticket store: the hub's own store. Joe would rather not use GitHub Issues.
- Herdr as the session layer on the workers (first to try), or plain tmux over SSH. AgentConnect is no longer needed with one controller.
- Plan terms for subscription logins on always-on daemons.
