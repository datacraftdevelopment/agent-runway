# CLAUDE.md

This file orients Claude Code when working in this repository.

> **Runway Agent** (personal project), scaffolded 2026-10-22 from the pm-sp starter. Concept: `docs/concept.md`.
>
> **This repo is PUBLIC.** No client names, client code, credentials, private hostnames or personal paths in code, docs, issues or examples.

## What this is

The project-management layer around this project, kept light: the scaffold
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
│   │   └── issue-tracker.md ← where maps live: docs/maps/
│   └── quirks.md        ← technical gotchas, fast capture
└── _pm/                 ← PERSONAL log: per person, append-only, never authoritative
    ├── README.md
    ├── skeleton.md      ← the macro why. Always populated.
    └── sessions/        ← one file per session: YYYY-MM-DD-<name>[-N].md
```

**The one rule:** `docs/` is authoritative; `_pm/` records what I did and
what I'm doing, never what is true.

## How we work

The workflow is Agent Runway's (the `agent-runway` plugin), with pm-sp's
skills around the session. Shaped work becomes tickets of two kinds: Runway
tickets run on their own; hands-on tickets are done here, in your own
session.

- **Open with `whats-next`, close with `stepping-away`.** Several sessions a
  day is normal.
- **New work is shaped first:** `grill` talks it through, `prototype` shows it
  when seeing beats reading, and `spec` writes it up. A quick, fully specified
  task skips it.
- **Screens come first.** Work with screens goes data sample, then screens in
  Claude Design (`design-handoff`), approved, then the spec.
- **Specs go in `docs/specs/YYYY-MM-DD-<topic>.md`, plans in
  `docs/plans/YYYY-MM-DD-<feature>.md`.** Both are committed.
- **Every spec has `## Acceptance`:** three to six observable checks as
  `- [ ] A1: …` lines, each saying how to verify it. Runway's reviewer walks
  them on every ticket; `ship-acceptance` runs them again against the real
  candidate and production.
- **An approved spec is not a go to file.** Ask; the user may want to sit on
  it.
- **`file-tickets` sorts the work:** a Runway ticket when an unattended agent
  can prove every Acceptance line, a hands-on ticket when one needs a real
  device or camera, or the user's eye on how it looks and feels. Filed only on
  the user's typed go.
- **Hands-on tickets** run in this session with `hands-on`: a plan
  (`writing-plans`) run by `subagent-driven-development` or `executing-plans`,
  test-first, the user checks what only they can, then `runway done` on their
  go. Decisions the plan didn't settle are made and written in the ledger as
  rulings; only irreversible, security, outside-the-worktree or hopelessly
  broken steps stop to ask.
- **Second opinion** (`second-opinion`, Sol through Ringer plus a fresh
  Opus): on project-sized specs before they're filed. Runway's two fresh
  reviews cover every ticket.
- **Foggy work** with several unknowns that depend on each other: suggest
  `map` (never started on its own). It holds decisions, never builds; its
  destination is a set of chunks in order, and each chunk gets its own spec.
- **Bugs:** `systematic-debugging`. Reproduce before fixing.
- **Model economy.** Subagents always name their model: `sonnet` to build,
  `opus` for judgment and the final review, never Fable or Haiku, whatever
  the main session runs on. Ordinary sessions run Opus in Claude Code and Sol
  in Codex. The same two read a project-sized spec fresh as the second
  opinion; no premium review seat.

## The taxonomy: known folders, created on first write

**Never pre-create a folder.** Each exists the moment something is first
written into it (`mkdir -p`, then write): presence means it was needed.

| Folder | Purpose | Sprout when |
|---|---|---|
| `docs/specs/` | Specs from `spec`, with Acceptance | the first spec is written |
| `docs/plans/` | Plans for hands-on work, from writing-plans | the first plan is written |
| `docs/shipped/` | Delivery records from ship-acceptance | the first acceptance run |
| `docs/notes/` | Scratch, meeting notes, ad-hoc analysis | first ad-hoc doc that isn't workflow |
| `knowledge/` | Curated project knowledge, always an OKF bundle (`okf` skill) | facts turn entity-shaped, or a second consumer needs them |
| `resources/` | Material **you bring in** from outside (`design-handoff/`, `research/`, `history/` as needed) | first external file arrives |
| `docs/adr/` | Durable decisions, in domain-modeling's format | the first ADR |
| `docs/maps/<effort>/` | A map, its decisions and research notes (`docs/agents/issue-tracker.md`) | `map` charts its first map |
| `.runway/` | Gitignored working state: plan ledgers and review packages for hands-on work | the first plan run |
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
scope) when the work is clear; a fuzzy start leaves it unset and the first
re-aim sets it; `stepping-away` closes with Shipped / Tried-Learned-Decided /
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

(The full rule: Agent Runway's `verification-before-completion` skill.)

## Delivery acceptance

When a spec's tickets have all merged, `ship-acceptance` runs its Acceptance
checks against the actual candidate, records the result in `docs/shipped/`,
and repeats them against production after the human deploys. Merged tickets
are not a delivered spec.
