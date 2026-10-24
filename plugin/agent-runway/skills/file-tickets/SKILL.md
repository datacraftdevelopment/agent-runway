---
name: file-tickets
description: "Propose tickets for Runway from this session, and file them only when the person types go. Use when the person asks to file work for Runway, hand parts of the work off to run on their own, queue tickets, or says 'file these', 'send these to Runway', 'run these unattended'. Also when you notice parts of the current work could run on their own: propose, never file unasked."
---

# File tickets for Runway

Runway runs each ticket headless on a free runner, has the other agent review it, and brings it back as a pull
request: merged on its own when it is low risk, otherwise waiting for the person. This skill turns part of the work in
this session into a small batch of tickets. **The person's typed go is the approval. Never file without it.**

## 1. Find Runway and the repo

Run each of these as its own command (no `&&`, `||` or `;`: a session with an allow-list refuses chained commands):

```bash
command -v runway
```

If it prints a path, run it as plain `runway` (not by that path: permission rules name the command). If it prints
nothing, use the copy inside the app: `/Applications/Runway.app/Contents/Resources/cli/bin/runway`. Call whichever
you use `RUNWAY` below, then:

```bash
RUNWAY repo which
```

- `repo which` prints the name Runway knows this repo by. If it says the repo isn't watched, stop and tell the
  person to add it in Runway's setup screen (or `runway repo add <path>`), then come back.
- No `runway` at all on this Mac: see "From another Mac" or "From a cloud session" below.

## 2. Propose the batch

Pick work that can run unattended: each ticket small, with an observable result, and not waiting on a decision only
the person can make. Two to five tickets is a good batch. Show it as one table, then ask:

| key | title | risk | agent | waits on | runs on |
| --- | --- | --- | --- | --- | --- |
| a | Print view for a single recipe | low: new page, no data changes | any | nothing | any |
| b | Search recipes by ingredient | not low: changes the database query | claude | a | any |

- **risk** is `low` only with a one-line reason. When unsure, it is `not low`: that ticket waits for the person
  instead of merging on its own. Anything touching auth, payments, data migrations, CI or secrets is `not low`.
- **agent** is `any`, `claude` or `codex`. Prefer `any` unless one of them is clearly better for it.
- **waits on** names another key in this batch, or a ticket id already filed (T-12), or nothing.
- **runs on** is `any`, or one runner by name when the work needs something only that machine has.

Under the table, give each ticket's Acceptance lines: one to three observable checks, each with how to verify it (a
command where there is one). Then ask, in your own words: "File these N tickets?" and **stop**. Do not file in the
same turn.

## 3. File on go

Only when the person's next message says go (go, yes, file them, ship it) for this batch. If they change something,
show the table again and ask again. A go for an earlier batch is not a go for a changed one.

Write the batch as JSON to a file in a temporary folder (with your file tool, not a shell heredoc), then file it with
one plain command:

```json
{"repo": "<name from repo which>",
 "tickets": [
  {"key": "a", "title": "...", "body": "what to build, and where",
   "acceptance": ["A1: ... Verify: <command>"],
   "risk": "low", "risk_reason": "one line", "agent": "any", "touches": ["path/or/area"], "blocked_by": []},
  {"key": "b", "title": "...", "body": "...", "acceptance": ["A1: ..."],
   "risk": "not-low", "agent": "claude", "blocked_by": ["a"], "runs_on": null}
 ]}
```

```bash
RUNWAY file --batch /tmp/runway-batch.json --filed-from "Claude Code session"
```

(In Codex, write `--filed-from "Codex session"`.) `runway file` checks the whole batch first and files all of it or
none: a low risk with no reason, an unknown runner or a missing Acceptance line is refused with the reason. Fix it and
run it again. Then tell the person the ids it printed. They show under Up next in Runway.

Point the body at the spec or plan when there is one (`docs/specs/...`); don't restate it.

## From another Mac

When Runway runs on another Mac (the person tells you which), file over SSH with the same JSON:

```bash
ssh <runway-mac> 'zsh -lc "runway file --filed-from \"Claude Code on another Mac\""' < /tmp/runway-batch.json
```

That needs `runway` on the Runway Mac's PATH (Runway's setup screen, step 1, "runway in Terminal").

## From a cloud session

Not yet. A cloud session can't reach the Runway Mac, and Runway can't yet import tickets pushed to a
`runway/tickets` branch (`runway import` isn't built). Say so, and offer to write the batch as JSON for the person to
file from their Mac with `runway file`.

## Never

- File without the person's typed go for this exact batch, or file more than they agreed to.
- Mark a ticket low risk to get it merged faster.
- Edit Runway's database or its files directly. Everything goes through `runway`.
