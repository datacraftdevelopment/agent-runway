---
name: map
description: "Chart work that is too big or too foggy for one session as a map of the decisions it needs, then settle them one at a time across sessions until the way is clear. Use when the person says 'map this', 'chart a map', 'work the map', or opens an existing map. For big or vague work, suggest it; don't start it unasked."
---

# Map big work

Some work is too big to spec in one go: several unknowns, each depending on others. A map breaks it into the
decisions that have to be made, in the order they can be made, and keeps them in the repo so any later session can
pick up where the last one stopped. A map holds decisions, never builds. Its end is a list of chunks, each small
enough to spec and ticket on its own.

## Where it lives

`docs/maps/<effort>/` in the repo:

- `MAP.md`: the destination in two or three sentences, then the decisions as a checklist, each with its status
  (`open`, `settled`, `dropped`) and what it waits on.
- `<nn>-<decision>.md`: one file per decision once work on it starts: the question, the options looked at, the
  answer and why. Research notes go in the same file.

Create the folder only when the first map is written.

## Charting a new map

1. Ask for, or work out with the person, the **destination**: what is true when this is done. Write it down first.
2. List the decisions between here and there. A decision is a question with more than one reasonable answer
   ("Which store holds sessions?"), not a task ("Build login").
3. Order them by what waits on what. Mark the ones that can be settled now.
4. Show the map and ask which decision to take first. Recommend one.

## Working the map

1. Open `MAP.md` and say where things stand in two lines: settled, open, next up.
2. Take one decision. Read what you need, try a prototype if seeing would settle it, and ask the person the
   questions only they can answer (one at a time, as in `grill`).
3. Write the answer into its file, mark it settled on the map, and note any decision it adds or removes.
4. Stop after one or two decisions a session. Say what is next.

## Done

When every decision is settled or dropped, the map's last section lists the **chunks**: pieces of work in order,
each a sentence or two. Each chunk then gets its own `spec`, and from there `file-tickets`.
