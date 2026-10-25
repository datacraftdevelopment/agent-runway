---
name: spec
description: "Write what this session has worked out into a spec that an unattended agent can build from and check against: what it does, what it doesn't, and acceptance checks. Use when the person says 'write the spec', 'spec this', 'write it up', or when a discussion has settled what to build and tickets come next."
---

# Write the spec

The spec is what every ticket worker and reviewer reads instead of this conversation. Write it from what has
already been said in this session and what the repo shows. Don't start a fresh interview: if something that
changes what gets built is still open, ask about that one thing (as in `grill`), and leave the rest.

## Where

`docs/specs/YYYY-MM-DD-<topic>.md` in the repo, unless the repo already keeps specs somewhere else. Create the
folder only when the first spec is written.

## What goes in it

```markdown
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
- Three to six for a spec. If you need more, the spec is probably two specs.

## After

Show the spec, fix what the person changes, and commit it. Then offer `file-tickets` to break it into tickets.
