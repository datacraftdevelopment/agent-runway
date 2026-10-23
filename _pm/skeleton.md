# Skeleton — Runway Agent

> Drafted 2026-10-22 from Joe's conversation shaping the concept (`docs/concept.md`). Joe to confirm or correct.

## Outcome

After the first release, **Joe** can shape work by hand, have the resulting tickets picked up and finished unattended on whichever of his machines (or a cloud session) is free, and see and answer everything from any machine's app.

## The one user journey that must stay intact

1. Joe shapes a piece of work in a steered session (pm-sp: wayfinder, brainstorm, plan), and a skill files the tickets into the hub with a risk level.
2. A daemon on a free machine claims a ticket and starts a Claude Code or Codex session in a worktree.
3. The session builds it, a second model reviews it, and a PR is opened.
4. Low risk and a passed review: it merges on its own. Anything else becomes a "needs you" card.
5. Joe sees the card on any machine's board and answers yes or no from there.

## Minimum capabilities

- Hub with a ticket store and live status (machines, sessions, tickets).
- Daemon per machine: connect out, heartbeat, claim, start a session, report receipts.
- Board app per machine: own machine or whole fleet, start/stop/pause the daemon, answer decisions for any machine.
- pm-sp contract: file tickets with risk, register every session, worker receipts.
- Review and risk-gated merge.

## Fundamental enablers

- Each machine's own Claude and Codex sign-ins; GitHub access for PRs.
- Network between machines and the hub that exposes nothing publicly (for example Tailscale).
- Approval only from Joe's own words or clicks.
- Credentials stay in each machine's keychain or environment, never in the repo or the hub.

## Non-negotiables

- Loop first: one real ticket runs end to end before any board polish.
- Client work never leaves infrastructure the user controls, and never lands in this public repo (no client names, code or credentials in code, issues or examples).
- No hidden background process: the daemon is visible and switchable in the app.
- Sensitive paths (auth, payments, migrations, CI) never auto-merge.
