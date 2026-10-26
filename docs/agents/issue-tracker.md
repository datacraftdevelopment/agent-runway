# Maps: local Markdown, in docs/maps/

Preset by the pm-sp plugin. Build work lives in Runway tickets (Runway and
hands-on) filed from a spec by Agent Runway's `file-tickets`, never in this
folder. `docs/maps/` holds only maps: Agent Runway's `map` skill charts
foggy efforts there as decisions to settle one at a time, committed with the
rest of the project's record.

## Conventions

- One effort per directory: `docs/maps/<effort>/`
- The map is `docs/maps/<effort>/map.md`: the destination, the decisions so
  far, and at the end the chunks, each of which gets its own spec.
- Decisions are one file each at `docs/maps/<effort>/issues/<NN>-<slug>.md`,
  numbered from `01`, never a single combined file
- State is a `Status:` line near the top of each file (`open`, `claimed`,
  `resolved`), with a `Blocked by:` line (numbers, or `none`)
- Research notes go next to the decision,
  `docs/maps/<effort>/research/<slug>.md`

## Sync

The map travels by git. After charting and after each resolved decision,
commit only `docs/maps/<effort>/` and push it to the default branch (standing
permission: map files only, never code), so the other computer and cloud
sessions see it on their next pull. Never mix code into a map commit. If the
session is on a feature branch, commit the map on the default branch from a
worktree, or say it is waiting to be pushed.

## One header line pm-sp reads

- **`Waiting on:`**: who, what, since when. A decision that needs the user's
  answer carries it; `whats-next` lists it under *Waiting on you*.

Loose ideas never go here; they go to `docs/inbox.md`.
