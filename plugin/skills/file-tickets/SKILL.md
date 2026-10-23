---
name: file-tickets
description: Turn finished shaping (a pm-sp plan and its design doc, a wayfinder map's destination chunks, or any spec with an Acceptance section) into Runway Agent tickets in the controller's store, each with its risk set, so they can run unattended. Use when shaping is done and the user says "file the tickets", "send this to Runway", "queue this up", "make tickets from the plan", or asks what would run unattended.
---

# File tickets

Shaping happens by hand with the operator. This skill is the hand-off at its end: it cuts the shaped work into tickets the controller can dispatch, shows the operator the batch, and files it on their go.

Tickets live in the controller's SQLite store, not in the repo. Specs and plans stay in git; a ticket points at them and never restates them.

## 1. Find what was shaped

Read, in this order, whichever exists:

- A pm-sp plan in `docs/plans/` and the design doc it names in `docs/specs/` (its `## Acceptance` lines).
- A wayfinder map's destination chunks (`docs/maps/<effort>/map.md`). A chunk that has no design doc yet is not ready to file; say so and stop for that chunk.
- Any spec file with an Acceptance section (Matt Pocock's `/to-spec`, a hand-written one).

The spec and plan must be committed on the default branch and pushed before filing: workers read them from a fresh checkout. If they aren't, say so and offer to push them.

## 2. Cut it into tickets

- **One ticket = one branch = one PR**, sized for one unattended session. A plan's tasks stay inside the ticket as commits.
- Split only where the pieces can merge on their own. Pieces that touch the same files go in one ticket or get a `--blocked-by`.
- Each ticket names the Acceptance lines it must satisfy, copied word for word from the spec.
- `--touches`: the paths you expect it to change. The reviewer compares the diff against them.

## 3. Set risk

Default `not-low`. Mark a ticket `low` only when all of these hold, and write the reason in one line:

- It touches none of: auth, payments or billing, data migrations or schema, CI or deploy config, credentials, deletes, a public interface others depend on, `runway.json`.
- Its Acceptance lines can be checked by the repo's own tests or CI.
- A wrong merge is cheap to revert.

`low` only allows an auto-merge after a passing review on the other model, green checks and the gate's own path check. The reviewer can raise risk later; nothing can lower it. When unsure, `not-low`.

## 4. Show the batch, file on the operator's go

Show one table: ref order, title, risk (with the low reason), blocked by, touches. Ask once. The operator's own message is the go; nothing else counts.

Then file each ticket in order, so `--blocked-by` refs exist:

```bash
runway-agent ticket add <PROJECT> \
  --title "Add the --dry-run flag to export" \
  --spec docs/specs/2026-10-23-export-design.md \
  --plan docs/plans/2026-10-23-export.md \
  --acceptance "- [ ] A2: export --dry-run prints the rows it would write and writes nothing" \
  --risk low --risk-reason "one module and its tests; covered by CI" \
  --touches src/export.py --touches tests/test_export.py \
  --blocked-by DEMO-3
```

It prints the new ref (`DEMO-4`). Not on the controller? Run the same command over SSH: `ssh <controller> runway-agent ticket add …`. A cloud session can't reach the controller: write the batch as the commands above in a reply for the operator to run.

Options: `--model claude|codex` when the builder model matters; `--strategy swarm` only when the operator asks for it (v1 doesn't run swarms; the ticket waits). `--body` is for context the spec doesn't hold, such as which plan tasks this ticket covers.

If the project isn't registered yet: `runway-agent project add <KEY> --repo owner/name --path <controller clone>`.

## 5. Report

List the refs filed and `runway-agent ticket list --project <KEY>`. Don't dispatch; the controller does.
