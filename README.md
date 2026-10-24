# Agent Runway

One board that dispatches coding tickets to agents on many machines and cloud sessions. Concept: `docs/concept.md`.

Website: `site/` (static, hosted on Vercel at agentrunway.app). Bugs and ideas: [open an issue](https://github.com/datacraftdevelopment/agent-runway/issues/new/choose).

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

## Licence

Source available under the [PolyForm Shield License 1.0.0](LICENSE): free to use, change and share for any purpose except providing a product that competes with Agent Runway. Third-party code vendored into this repo keeps its own licence, recorded beside it.

Contributions: see [CONTRIBUTING.md](CONTRIBUTING.md). Pull requests need the [Contributor Licence Agreement](CLA.md), which a check asks for once.
