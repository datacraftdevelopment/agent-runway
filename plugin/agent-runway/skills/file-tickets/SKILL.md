---
name: file-tickets
description: "Propose tickets for Runway from this session, and file them only when the person types go. Use in a repo added to Runway when the spec says runway: yes, or when the person asks to file work for Runway, queue tickets, or says 'file these', 'send these to Runway', 'run these unattended'. Never in a repo that isn't in Runway unless the person asks for it."
---

# File tickets for Runway

Runway runs each ticket headless on a free runner, reviews it in two fresh sessions (the code, then the function
against its Acceptance lines), and brings it back as a pull request: merged on its own when it is low risk, otherwise
waiting for the person. One engine (Claude Code or Codex) is enough. This skill turns part of the work in
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

- `repo which` prints the name Runway knows this repo by. If it says the repo isn't watched, this repo doesn't use
  Runway: stop here and build the work in this session instead (see the `spec` skill's After). Only if the person
  asked for Runway in so many words, tell them it can be added in Runway's setup screen (or `runway repo add <path>`).
- No `runway` at all on this Mac: see "From another Mac" or "From a cloud session" below.

## 2. Propose the batch

Each ticket small, with an observable result, and not waiting on a decision only the person can make. Two to five
tickets is a good batch. Sort every ticket into one of two kinds:

- **Runway**: an unattended agent can build it and prove each Acceptance line (a test, a command, a screenshot it can
  take, an experiment in a throwaway copy). Most work is this.
- **hands-on**: some Acceptance line needs a real device or camera, or the person's eye on how it looks or feels
  (motion, a sheet that settles, a colour that reads). Runway never starts these; the person does them in their own
  session with the `hands-on` skill. A build that's slow, or a tool the setup lacks, is not a reason: that is a setup
  problem for `runway doctor`, not hands-on work.

When one ticket mixes both, split it: the provable part is a Runway ticket, and the part the person must check is a
hands-on ticket. Show the batch as one table, then ask:

| key | title | kind | risk | agent | waits on | runs on |
| --- | --- | --- | --- | --- | --- | --- |
| a | Store each session's frame size | Runway | low: new column, no migration of old rows | any | nothing | any |
| b | Camera preview fills the frame on a phone | hands-on | not low: camera code | any | a | any |
| c | Show the frame size in the history list | Runway | low: new label | any | nothing | any |

- **risk** is `low` only with a one-line reason. When unsure, it is `not low`: that ticket waits for the person
  instead of merging on its own. Anything touching auth, payments, data migrations, CI or secrets is `not low`.
- **agent** is `any`, or an engine this Mac has. Check which with `RUNWAY status --json` (its `agents` list holds
  only the engines that are set up), and propose only those. With one engine, use `any`. Runway refuses a ticket
  for an engine it doesn't have.
- **waits on** names another key in this batch, or a ticket id already filed (T-12), or nothing. A Runway ticket
  waits on a hands-on one only when it truly needs that work in place (or changes the same files): the rest run while
  the person does the hands-on ones. Say in a line under the table which Runway tickets wait on hands-on work.
- **runs on** is `any`, or one runner by name when the work needs something only that machine has.

Under the table, give each ticket's Acceptance lines: one to three observable checks, each with how to verify it (a
command where there is one). Write lines a fresh reviewer can verify from the repo alone, with the repo's own
commands: a test or command it runs, or an experiment it can do and undo (change a value, see a named test fail).
Not something that needs a person, a phone, a camera or a file that isn't in the repo. Then ask, in your own words: "File these N tickets?" and **stop**. Do not file in the
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
   "risk": "not-low", "agent": "claude", "blocked_by": ["a"], "runs_on": null},
  {"key": "c", "title": "...", "body": "...", "acceptance": ["A1: ... Check on the phone: <what to look for>"],
   "risk": "not-low", "hands_on": true, "blocked_by": ["a"]}
 ]}
```

```bash
RUNWAY file --batch /tmp/runway-batch.json --filed-from "Claude Code session"
```

(In Codex, write `--filed-from "Codex session"`.) `runway file` checks the whole batch first and files all of it or
none: a low risk with no reason, an unknown runner or a missing Acceptance line is refused with the reason. Fix it and
run it again. Then tell the person the ids it printed. They show under Up next in Runway, the hands-on ones marked as
theirs. If the batch has hands-on tickets, offer to start them now with the `hands-on` skill.

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
