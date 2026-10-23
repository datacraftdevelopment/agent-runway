---
name: to-tickets
description: "Break a chunk's spec into tracer-bullet tickets, each declaring its blocking edges, its risk and the areas it touches, as one file per ticket in docs/maps/<effort>/tickets/, checked by the readiness check and filed only on the user's go. Use after to-spec, or when the user says \"cut the tickets\", \"to-tickets\", \"file tickets\"."
disable-model-invocation: true
---

<!-- pm-runway: our version of Matt Pocock's to-tickets (mattpocock/skills 5beb35b). Changes are listed in VENDOR.md and marked "pm-runway" below. -->

# To Tickets

Break a plan, spec, or conversation into a set of **tickets**: tracer-bullet vertical slices, each declaring the tickets that **block** it.

pm-runway: the tracker is local files. Tickets for one chunk live in `docs/maps/<effort>/tickets/`, where `<effort>` is the wayfinder map the chunk came from, or the chunk's own slug when there was no map. Wayfinder's decision tickets stay in `docs/maps/<effort>/issues/`; the two never mix. Each ticket will be built by a fresh session on a machine nobody is watching, so every rule in `RUNWAY.md` (at the plugin root) is a hard rule here, not advice.

## Process

### 1. Gather context

Work from whatever is already in the conversation context. If the user passes a reference (a spec path, an issue number or URL) as an argument, fetch it and read its full body and comments. pm-runway: the spec in `docs/specs/` is required; if there isn't one, offer `to-spec` first.

### 2. Explore the codebase (optional)

If you have not already explored the codebase, do so to understand the current state of the code. Ticket titles and descriptions should use the project's domain glossary vocabulary, and respect ADRs in the area you're touching.

Look for opportunities to prefactor the code to make the implementation easier. "Make the change easy, then make the easy change."

### 3. Draft vertical slices

Break the work into **tracer bullet** tickets.

<vertical-slice-rules>

- Each slice cuts a narrow but COMPLETE path through every layer (schema, API, UI, tests): vertical, NOT a horizontal slice of one layer
- A completed slice is demoable or verifiable on its own
- Each slice is sized to fit in a single fresh context window
- Any prefactoring should be done first

</vertical-slice-rules>

Give each ticket its **blocking edges**: the other tickets that must complete before it can start. A ticket with no blockers can start immediately.

**Wide refactors are the exception to vertical slicing.** A **wide refactor** is one mechanical change (rename a column, retype a shared symbol) whose **blast radius** fans across the whole codebase, so a single edit breaks thousands of call sites at once and no vertical slice can land green. Don't force it into a tracer bullet; sequence it as **expand–contract**. First expand: add the new form beside the old so nothing breaks. Then migrate the call sites over in batches sized by blast radius (per package, per directory), each batch its own ticket blocked by the expand, keeping CI green batch to batch because the old form still exists. Finally contract: delete the old form once no caller remains, in a ticket blocked by every migrate batch. When even the batches can't stay green alone, keep the sequence but let them share an integration branch that all block a final integrate-and-verify ticket; green is promised only there.

pm-runway: also give each ticket

- **touches**: the areas it changes (`web/inbox`, `api/messages`), named loosely, never exact file paths. The loop never runs two tickets that touch the same area at once.
- **risk**: the spec's risk, or higher for this ticket. A `low` ticket needs a one-line `risk_reason`. A ticket can never be lower than its spec.
- **model**: `any`, unless the ticket needs one (`claude` or `codex`). The reviewer is always the other one.
- **Acceptance**: every line with a `Verify:` a stranger can run in the worker's checkout: a test command, or a short manual procedure. No line that needs outside setup the repo doesn't hold (a key, a running service); if the ticket needs one, it isn't ready, and that goes in the quiz.

### 4. Quiz the user

Present the proposed breakdown as a numbered list. For each ticket, show:

- **Title**: short descriptive name
- **Blocked by**: which other tickets (if any) must complete first
- **What it delivers**: the end-to-end behaviour this ticket makes work
- pm-runway: **Risk** and **touches**

Ask the user:

- Does the granularity feel right? (too coarse / too fine)
- Are the blocking edges correct: does each ticket only depend on tickets that genuinely gate it?
- Should any tickets be merged or split further?
- pm-runway: is any risk wrong? Is anything here that a person should do instead?

Iterate until the user approves the breakdown.

### 5. Write, check, and file on the user's go

pm-runway: write one file per ticket as `docs/maps/<effort>/tickets/<NN>-<slug>.md`, numbered from `01` in dependency order (blockers first), with `status: draft`, using the template below. Then run the readiness check:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/runway/runway.py" check docs/maps/<effort>/tickets
```

Fix every `NOT READY` line; never weaken a ticket to make the check pass (a vague Verify, a missing blocker). When it is clean, show the user the list once more and ask for the go. On the go, set every ticket to `status: ready-for-agent`, commit only the tickets folder on the default branch (`tickets: <chunk>`), push, and tell the user the next step is `runway start` (the `implement-spec` skill). Filing is not starting: nothing runs until the user starts the chunk.

Work the **frontier**: any ticket whose blockers are all done. For a purely linear chain that means top to bottom.

Do NOT close or modify any parent issue.

<local-ticket-template>

---
id: <chunk>-<NN>                 # lowercase, digits, dashes; unique
chunk: <chunk>
spec: docs/specs/<date>-<chunk>.md
blocked_by: [<chunk>-01]          # or []
touches: [web/inbox, api/messages]
risk: not-low                     # or low, with risk_reason
risk_reason: ""
model: any                        # claude | codex | any
status: draft                     # ready-for-agent once the user says go
---
# <Ticket title>

## What to build

The end-to-end behaviour this ticket makes work, from the user's perspective, not a layer-by-layer implementation list.

## Blocked by

The ids and titles of the tickets that gate this one, or "None (can start immediately)".

## Acceptance

- [ ] A1: <observable result>. Verify: `<command>` (or a short manual procedure)
- [ ] A2: …

## Context

Spec: the spec path, the user stories this ticket serves, and the agreed test seam. Terms: GLOSSARY.md entries if any. Context by link, never copied.

## Out of scope

What a worker might be tempted to do here and must not.

</local-ticket-template>

In either form, avoid specific file paths or code snippets: they go stale fast. Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it and note briefly that it came from a prototype. Trim to the decision-rich parts, not a working demo, just the important bits.
