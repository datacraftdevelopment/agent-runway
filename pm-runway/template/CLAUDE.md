# CLAUDE.md

This file orients Claude Code when working in this repository.

> **This is a STARTER, not a live project.** `/pm-runway:scaffold` stamps it and
> replaces this banner with the project header. The scaffold is designed in
> the pm-runway plugin (`datacraftdevelopment/dc-dev-plugins`, `pm-runway/template/`);
> the workflow it serves is that plugin's `WORKFLOW.md`.

## What this is

The project-management layer around an engagement, kept light: the scaffold
holds only what every project uses from day one. Everything else is known but
not built (the taxonomy below). Agnostic to codebase: the deliverable might be
FileMaker, web, SaaS or pure consulting.

## Day-one layout

```
<project>/
├── CLAUDE.md            ← you are here
├── README.md
├── .gitignore
├── docs/                ← SHARED record: collaborators and clients read it
│   ├── inbox.md         ← loose ideas, one line each, no status
│   ├── agents/
│   │   └── issue-tracker.md ← where wayfinder keeps maps: docs/maps/
│   └── quirks.md        ← technical gotchas, fast capture
└── _pm/                 ← PERSONAL log: per person, append-only, never authoritative
    ├── README.md
    ├── skeleton.md      ← the macro why. Always populated.
    └── sessions/        ← one file per session: YYYY-MM-DD-<name>[-N].md
```

**The one rule:** `docs/` is authoritative; `_pm/` records what I did and
what I'm doing, never what is true.

## How we work

The workflow is the pm-runway plugin's: Superpowers' skills for the work, pm-runway's
around the session.

- **Open with `whats-next`, close with `stepping-away`.** Several sessions a
  day is normal.
- **New work starts in `brainstorming`.** It reads the project first, talks it
  through, shows mockups in a browser tab when seeing beats reading, lays out
  approaches and writes a design doc. A quick, fully specified task skips it.
- **Screens come first.** Work with screens goes data sample, then screens in
  Claude Design (`design-handoff`), approved, then build.
- **Design docs go in `docs/specs/YYYY-MM-DD-<topic>-design.md`, plans in
  `docs/plans/YYYY-MM-DD-<feature>.md`.** Both are committed.
- **Every design doc has `## Acceptance`:** three or four observable checks as
  `- [ ] A1: …` lines. `ship-acceptance` runs them later against the real
  candidate and production.
- **An approved design is not a go to plan.** Ask; the user may want to sit on
  it.
- **Run the plan in one session:** `subagent-driven-development` (a fresh
  subagent per task, reviewed) or `executing-plans` (inline). Task = commit,
  never a session. Decisions the plan didn't settle are made and written in the
  ledger as rulings; only irreversible, security, outside-the-worktree or
  hopelessly broken steps stop to ask.
- **Second opinion** (`second-opinion`, Sol through Ringer plus a fresh
  Opus): on project-sized design docs during brainstorming's builder check,
  and on the finished branch before it merges. Not after every task.
- **Parallel lanes** go to `nested-sessions`, only when the plan marks lanes
  with disjoint files and the user wants them moving at once.
- **Foggy work** with several unknowns that depend on each other: suggest
  `wayfinder` (it runs when the user names it, never on its own). Its tickets are decisions, never builds; its destination is a set of
  chunks in order, and each chunk gets its own brainstorm.
- **Bugs:** `systematic-debugging`. Reproduce before fixing.
- **Model economy.** Subagents and nested sessions always name their model:
  `sonnet` to build, `opus` for judgment and the final review, never Fable or
  Haiku, whatever the main session runs on. Ordinary sessions run Opus in
  Claude Code and Sol in Codex. The same two read each design and branch fresh as the second
  opinion; no premium review seat.

## The taxonomy: known folders, created on first write

**Never pre-create a folder.** Each exists the moment something is first
written into it (`mkdir -p`, then write): presence means it was needed.

| Folder | Purpose | Sprout when |
|---|---|---|
| `docs/specs/` | Design docs from brainstorming, with Acceptance | the first design is written |
| `docs/plans/` | Implementation plans from writing-plans | the first plan is written |
| `docs/shipped/` | Delivery records from ship-acceptance | the first acceptance run |
| `docs/notes/` | Scratch, meeting notes, ad-hoc analysis | first ad-hoc doc that isn't workflow |
| `knowledge/` | Curated project knowledge, always an OKF bundle (`okf` skill) | facts turn entity-shaped, or a second consumer needs them |
| `resources/` | Material **you bring in** from outside (`design-handoff/`, `research/`, `history/` as needed) | first external file arrives |
| `docs/adr/` | Durable decisions, in domain-modeling's format | the first ADR |
| `docs/maps/<effort>/` | A wayfinder map, its decision tickets and research notes (`docs/agents/issue-tracker.md`) | `/pm-runway:wayfinder` charts its first map |
| `.superpowers/` | Gitignored working state: plan ledgers, review packages, brainstorming mockups | the first plan run or visual brainstorm |
| `docs/agents/client-face.md` | Optional: names a client-facing tracker and its close-out steps; `stepping-away` follows it | the client-face tool's own setup writes it |
| `_pm/transcripts/` | Meeting transcripts, **gitignored** | first transcript kept (`granola-transcript`) |
| `_pm/artifacts/` | Other raw inputs: customer docs, exports, recordings | first raw input that isn't a transcript |
| `_pm/deliverables/` | What you hand to the client: reports, dashboards | first deliverable produced |
| `_app/` · `_ws/` · … | Code surfaces, **one underscore container per surface** | the surface becomes real |

Claude-generated docs go in `docs/`; external material goes in `resources/`.
Provenance decides, not file type.

## The skeleton

`_pm/skeleton.md`: outcome sentence, critical user journey, minimum
capabilities, fundamental enablers, non-negotiables. A paragraph for a
change-request job, a longer doc for a six-month engagement.

## Sessions and the Intent block

One file per session, per person, append-only. `whats-next` writes a two or
three sentence Intent at the open (push, why, done-for-this-session, not in
scope); `stepping-away` closes with Shipped / Tried-Learned-Decided /
Intent-vs-outcome and a resumable line per plan in flight. Keep the session's
exact path and ID in the conversation; close by that binding. `checkpoint`
appends a dated re-aim only when the session can't be broken.

## Verifying your work

Before reporting any task done, fixed or passing:

- **Run the check fresh**, after the last edit, and **show its output**:
  tests, build, lint, a real request, a screenshot, whichever would catch the
  failure you'd most plausibly have caused.
- The claim is exactly what the output supports. Red: report it verbatim.
  Partial: say which parts. Nothing runnable: say what *would* verify it.
- Fix the code, not the test. Never skip or delete a failing test, add a
  suppression or loosen a threshold to get green.

(The full rule: pm-runway's `verification-before-completion` skill.)

## Delivery acceptance

After the branch is finished, `ship-acceptance` runs the design doc's
Acceptance checks against the actual candidate, records the result in
`docs/shipped/`, and repeats them against production after the human deploys.
A green plan is not a delivered design.
