# Runway Agent

Shape work by hand, then let your own Macs build it while you're away. This repo holds:

- **`pm-runway/`**, the one plugin for the whole workflow: session and shaping skills, Matt Pocock's spec-to-tickets flow as our own versions, and Runway (a ticket format, a plain loop script that runs a chunk's tickets through [Orca](https://github.com/stablyai/orca) on your Macs, review by the other model, and a merge gate in code). Start with [`pm-runway/README.md`](pm-runway/README.md) and [`pm-runway/RUNWAY.md`](pm-runway/RUNWAY.md).
- **The setup kit:** [`SETUP.html`](SETUP.html) for a person, [`SETUP-AGENT.md`](SETUP-AGENT.md) for an agent to run, `setup/doctor.sh` to check a machine, and `setup/practice/`, a tiny repo with one three-ticket chunk that proves a setup end to end.

Install: `/plugin marketplace add datacraftdevelopment/dc-dev-plugins`, then `/plugin install pm-runway@dc-dev-plugins` (this repo is also a marketplace of its own: `/plugin marketplace add datacraftdevelopment/runway-agent`). Uses your own Claude Code and Codex CLI subscriptions. MIT.

Concept and history: `docs/concept.md`, `docs/specs/2026-10-23-pm-runway-design.md`.

---

Project-management scaffold for this project. Light by design: only the
day-one folders exist; everything else is created on first use (the taxonomy
lives in `CLAUDE.md`).

## Working the project

1. `_pm/skeleton.md` holds the outcome, journey and non-negotiables, written at
   scaffold time; keep it current as scope moves.
2. Open each session with `whats-next`; close it with `stepping-away`.
3. New work: `brainstorming` writes a design doc in `docs/specs/` with its
   Acceptance checks; `writing-plans` turns it into a plan in `docs/plans/`;
   one session runs the plan; `finishing-a-development-branch` wraps it up;
   `ship-acceptance` proves it against production.
4. Decisions that need their own record go to `docs/adr/`. Loose ideas go to
   `docs/inbox.md`.

Stamped by the pm-sp plugin's `/pm-sp:scaffold` (`datacraftdevelopment/dc-dev-plugins`).
The workflow of record is that plugin's `WORKFLOW.md`.
