---
name: spec
description: "Write what this session has worked out into a spec a fresh agent can build from and check against: what it does, what it doesn't, and acceptance checks. Use when the person says 'write the spec', 'spec this', 'write it up', or when a discussion has settled what to build."
---

# Write the spec

The spec is what every builder and reviewer reads instead of this conversation (a later session here, or Runway's
ticket workers in a repo that uses Runway). Write it from what has
already been said in this session and what the repo shows. Don't start a fresh interview: if something that
changes what gets built is still open, ask about that one thing (as in `grill`), and leave the rest.

## Where

`docs/specs/YYYY-MM-DD-<topic>.md` in the repo, unless the repo already keeps specs somewhere else. Create the
folder only when the first spec is written.

## What goes in it

```markdown
---
runway: <yes | no>   (only in a repo added to Runway, once it's decided: see After)
---
# <What is being built>

Status: spec, <date>. Risk: <low: one-line reason | not low>.

## Why
Two or three sentences: the problem and who has it.

## What it does
The behaviour, from the user's side. Short paragraphs or a list. Name screens, commands or endpoints by what
the person sees.

## Not in scope
What someone might expect that this deliberately leaves out.

## Decisions
Choices made along the way, one line each with its reason. Link a map or prototype if one settled it.

## Testing
Where the tests go in: the one or two places (a command, an API, a screen) the behaviour is checked from. Use the
repo's existing test style. Ticket workers test at these points, not inside the code they write.

## Acceptance
- [ ] A1: <an observable check>. Verify: <a command, a URL, or what to look at>.
- [ ] A2: …
```

## Risk

Settle it with the person in one line before you write. `low` needs a reason it can't hurt anything that matters
(copy, a new isolated screen, tests only). Anything touching auth, payments, data, migrations, CI or secrets is
`not low`, and so is anything you can't explain away in a line. `file-tickets` starts each ticket from this risk;
only low-risk tickets can merge without the person, and a reviewer can raise risk, never lower it.

## Acceptance lines

These are the part that matters most. Runway's reviewer walks each one, pass or fail, on the exact commit, and
`file-tickets` copies them into the tickets.

- Each line is observable: something a fresh agent can run or look at, not "works well".
- Each says how to verify it, with a command where there is one.
- A reviewer verifies them alone, in a fresh copy of the repo, with the repo's own commands: write lines it can run,
  or an experiment it can do and undo (change a value, see a named test fail). Something only a real device or camera,
  or the person's eye on how it looks and feels, can show isn't a line it can pass: mark it `(hands-on)` and say what
  the person checks. `file-tickets` makes those lines hands-on tickets, done in the person's own session.
- Three to six for a spec. If you need more, the spec is probably two specs.

## After: build it here, or in Runway

Show the spec, fix what the person changes, and commit it. Then decide where it's built, without pushing Runway:

1. **Is this repo in Runway?** Run `runway repo which` (if there's no `runway` command, it isn't). If it doesn't print
   this repo's name, Runway is out of the picture: don't mention it, don't offer tickets, don't ask. Build it here:
   a plan with `writing-plans`, then `subagent-driven-development` or `executing-plans`, test-first, with the person
   checking what only they can (`hands-on` covers that).
2. **Already decided?** If the spec's front matter says `runway: yes` or `runway: no`, follow it and don't ask again.
3. **A good fit?** Runway suits several independent pieces, each with Acceptance lines a fresh agent can check on its
   own. Work that's mostly one piece, or mostly a real device, a camera or the person's eye, is a poor fit: don't ask,
   write `runway: no` and build it here.
4. **Ask once:** "Run this through the Runway app, or do it here?" Write the answer into the spec's front matter
   (`runway: yes` or `runway: no`) and commit it. Yes: `file-tickets`. No: build it here, as in 1.
