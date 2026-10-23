# Issue tracker: Local Markdown, in docs/maps/

Preset by the pm-runway plugin. Two kinds of ticket live in `docs/maps/`,
committed with the rest of the project's record: `wayfinder`'s decision
tickets (`docs/maps/<effort>/issues/`) for foggy efforts, and build tickets
for the loop (`docs/maps/<effort>/tickets/`, written by `to-tickets`, format in
the plugin's `RUNWAY.md`). Hand-built work still lives in design docs and
plans. Switch to GitHub Issues by copying pm-runway's
`templates/issue-tracker-github.md` over this file. The conventions below are
Matt Pocock's local-markdown tracker, kept in `docs/maps/` instead of a scratch folder,
plus one descriptive header line pm-runway reads.

## Conventions

- One effort per directory: `docs/maps/<effort>/`
- The map is `docs/maps/<effort>/map.md`
- Decision tickets are one file each at `docs/maps/<effort>/issues/<NN>-<slug>.md`, numbered from `01`, never a single combined file
- State is a `Status:` line near the top of each ticket file
- Comments and conversation history append to the bottom of the file under a `## Comments` heading

## Build tickets (pm-runway)

- One chunk per folder: `docs/maps/<effort>/tickets/<NN>-<slug>.md`, numbered from `01` in dependency order. `<effort>` is the wayfinder map the chunk came from, or the chunk's slug when there was none.
- Each file starts with the YAML header `runway check` reads (`id`, `chunk`, `spec`, `blocked_by`, `touches`, `risk`, `model`, `status`); the body is Matt Pocock's ticket: What to build, Blocked by, Acceptance with a `Verify:` per line, Context, Out of scope.
- `status: draft` until the user says go, then `ready-for-agent`. Run state (building, in review, landed) is never written back into the files; it lives in the loop's journal on the controller and in Orca.
- Once a chunk has started, its ticket files are frozen: a change goes through the user and a new chunk.

## When a skill says "publish to the issue tracker"

Create a new file under `docs/maps/<effort>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the ticket number directly.

## Wayfinding operations

Used by `/pm-runway:wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `docs/maps/<effort>/map.md`, the Destination / Notes / Decisions-so-far / Not-yet-specified / Out-of-scope body.
- **Child ticket**: `docs/maps/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `resolved`.
- **Frontier**: scan `docs/maps/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`.
- **Sync**: the map travels by git. After charting and after each resolved ticket, commit only `docs/maps/<effort>/` (`wayfinder: <ticket title>`) and push it to the default branch (standing permission: map files only, never code), so the other computer and cloud sessions see it on their next pull. Never mix code into a map commit. If the session is on a feature branch, commit the map on the default branch from a worktree, or say it is waiting to be pushed.
- **Research findings**: write them next to the ticket, `docs/maps/<effort>/research/<slug>.md`, instead of a throwaway branch.

## One header line pm-runway reads

- **`Waiting on:`**: who, what, since when. A wayfinder ticket that needs
  the user's answer carries it; `whats-next` lists it under *Waiting on you*.

Loose ideas never go here; they go to `docs/inbox.md`.
