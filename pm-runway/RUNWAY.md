# Runway: tickets, the loop and the gate

The unattended half of pm-runway. You shape by hand (wayfinder when it's foggy, brainstorming, `to-spec`, `to-tickets`); from the moment you start a chunk, it runs on your machines without you, until its PR needs you or merges.

```
you                     the loop (a script, no model)           fresh Orca workers
---                     -----------------------------           ------------------
to-spec  -> spec
to-tickets -> tickets
runway start  ------->  journal: risk + blockers captured
runway loop   ------->  frontier -> worker-start --on <mac>  ->  work-ticket (tdd), push rw/<id>
                        worker_done -> branch on origin?     <-
                        other model  -> worker-start         ->  review-ticket on that exact commit
                        pass -> merge into chunk/<chunk>     <-
                        ... until every ticket has landed
                        whole-chunk review                   ->  code-review + Acceptance
                        chunk PR -> gate: merge, or you
runway-ask  <-------->  journal + Orca, read fresh
```

## The ticket file

`docs/maps/<effort>/tickets/<NN>-<slug>.md`: a small header for the loop, Matt Pocock's ticket body for the agent.

```markdown
---
id: inbox-v2-03
chunk: inbox-v2
spec: docs/specs/2026-10-23-inbox-v2.md
blocked_by: [inbox-v2-01]
touches: [web/inbox, api/messages]
risk: low
risk_reason: a read-only badge; no data changes
model: any
status: ready-for-agent
---
# Show unread count on the inbox tab

## What to build
The inbox tab shows how many messages are unread, and the number drops as soon as one is read.

## Blocked by
- inbox-v2-01 Unread flag on messages

## Acceptance
- [ ] A1: With 3 unread messages the tab reads "Inbox (3)". Verify: `npm test -- inbox-badge`
- [ ] A2: Reading one drops it to "(2)" without a reload. Verify: `npx playwright test inbox-badge`

## Context
Spec: docs/specs/2026-10-23-inbox-v2.md, user stories 4 to 6, test seam "InboxStore".

## Out of scope
Push notifications. A badge on the app icon.
```

| Field | Meaning |
|---|---|
| `id` | Unique, lowercase, digits and dashes. Usually `<chunk>-<NN>`. |
| `chunk` | The chunk this ticket belongs to; one chunk per folder. |
| `spec` | The chunk's spec. Context by link, never copied. |
| `blocked_by` | Tickets that must have **landed** on the chunk branch first, or `[]`. |
| `touches` | Areas, not file paths. Two tickets touching one area never run at once. |
| `risk` | `low` (with a one-line `risk_reason`) or `not-low`. Never lower than the spec. Review can raise it, never lower it. |
| `model` | `any`, `claude` or `codex`. The reviewer is always the other one. |
| `status` | `draft`, then `ready-for-agent` on your go. Run state is never written back here. |

## The readiness rules

`runway check <folder>` refuses a ticket that breaks one of these, and `runway start` refuses a chunk with one. They come from what Spec Kit, Kiro, Task Master, BMAD, Matt's to-tickets, Beads, Symphony and GitHub's Copilot guidance agree on, plus what unattended runs add.

1. **One fresh session.** Fits one context window, start to push. Split when it doesn't.
2. **A vertical slice.** Ends in something demoable or testable on its own.
3. **Checks a stranger can run.** Every Acceptance line has a `Verify:`.
4. **Context by link.** Points at the spec, its user stories and test seam; never restates them.
5. **Explicit blockers.** `blocked_by`, or `[]`. No cycles, no unknown ids.
6. **No outside setup.** Everything it needs is in the repo or on every worker. If not, it isn't ready.
7. **Risk set at shaping.** It decides who merges.
8. **A done-state.** Pushed branch, then `worker_done`, then review, then landing. Built is not done.

The checker enforces the shape of 1 to 8 (fields, sections, Verify lines, blockers, cycles); whether a slice really fits one session is for `to-tickets`' quiz.

## The loop

`runway loop --chunk <chunk>`, in an Orca terminal tab on the controller. Each tick it:

1. reads Orca's inbox for the chunk's run (`orca orchestration check --run …`): each `worker_done`, question and escalation;
2. records each result, checking the claim against git: a build counts only if `rw/<ticket>` is on origin; a review counts only for the commit it names, and only from the other model;
3. merges every passed ticket into `chunk/<chunk>`, runs `check_cmd`, pushes;
4. starts reviews, then builds on the frontier, within each machine's slots and `max_running`, never two on one area;
5. when every ticket has landed, starts the whole-chunk review, opens the chunk PR and runs the gate.

One fix pass per ticket: a failed build, a failed review or a merge conflict sends it back once, with the reason in the worker's prompt; the second failure waits for you. `runway pause` stops new work starting; running workers finish. The status screen redraws each tick, and `~/.pm-runway/board.html` (`runway board` prints its URL) shows Queued, Implementing, In review, Merged and Waiting on you for Orca's browser tab.

## The gate

`runway gate --chunk <chunk> --pr <n> [--merge]`, run by the loop at the end. It merges the chunk PR only when all of these hold, and otherwise leaves it for you with the reasons:

- every ticket landed, none dropped;
- the chunk is low risk: every ticket captured low at `runway start`, and no reviewer raised it;
- the whole-chunk review passed on the PR's head commit;
- checks on the head are green;
- no sensitive path changed (`runway.json`, CI config, ticket files, auth, payments, billing, migrations, SQL, Dockerfiles, plus the repo's own `sensitive_paths`);
- `runway.json` on the default branch doesn't turn `auto_merge` off.

The gate reads risk from the journal, `runway.json` from the default branch, and the head from GitHub: nothing a worker can edit.

## Where things live

| What | Where |
|---|---|
| Specs and tickets | the repo: `docs/specs/`, `docs/maps/<effort>/tickets/` |
| Per-repo rules | the repo: `runway.json` on the default branch (template: `templates/runway/runway.json`) |
| Machines, slots, agents | the controller: `~/.pm-runway/machines.json` (template: `templates/runway/machines.json`) |
| A chunk's journal | the controller: `~/.pm-runway/runs/<repo>--<chunk>.json` |
| Loop heartbeat and board | the controller: `~/.pm-runway/loop.json`, `board.html` |
| Live workers | Orca |

`PM_RUNWAY_HOME` moves `~/.pm-runway`.

## Not proven yet

Written against Orca's source and docs (stablyai/orca at `8d94ed06`, 2026-10-23), not yet run end to end. The first real run (one chunk, three tickets, two Macs) checks: the JSON shapes of `run-create`, `worker-start` and `check` (the loop reads ids tolerantly and fails loudly when it can't find one), reading a run's inbox from a plain terminal with `--run`, and `--on` plus `--repo` placement on a paired Mac.
