---
name: implement-spec
description: "Implement a chunk's spec and tickets unattended across your machines: start the chunk, run the loop in an Orca tab, and let fresh Orca workers build, review and land each ticket on the chunk's integration branch, then gate the chunk PR. Use after to-tickets has filed a chunk, or when the user says \"run the chunk\", \"start the loop\", \"implement-spec\"."
disable-model-invocation: true
---

<!-- pm-runway: our version of Matt Pocock's implement-spec (mattpocock/skills 5beb35b). His steps are kept; who does each one changed. See VENDOR.md. -->

# Implement a spec

The goal is the entire spec implemented on a single **integration branch** (`chunk/<chunk>`), with every ticket landed on it, then one PR from it to the default branch that the gate merges or hands to the user.

The tickets are not a list of steps. They are a **task graph** with blocking relationships between them, so there is always a **frontier** of tickets ready to be grabbed.

## Who does what

Matt's skill runs all of this from one session with background subagents. pm-runway spreads it across machines and takes the session out of the loop, so no coordinator's context grows with the chunk:

| Matt's step | pm-runway |
|---|---|
| Create the integration branch | `runway loop` pushes `chunk/<chunk>` from the base on its first tick |
| Implementer subagent per frontier ticket, own worktree, `tdd`, merges the integration tip before done | A fresh **Orca worker** per ticket on a free machine (`work-ticket`), up to each machine's slots |
| Merger subagent | The loop merges a ticket into `chunk/<chunk>` only after **review-ticket** passed on its exact commit, run by the other model |
| Kick off more as the frontier changes | Every tick |
| `code-review` on the integration branch, one fixer | A fresh whole-chunk review worker (`review-ticket`, Whole chunk) |
| Mark the PR ready | The **gate** (`runway gate`): merged automatically only when the chunk is low risk, every review passed on the head, checks are green and no sensitive path changed; otherwise it waits for the user |

The loop is a plain script. It holds no conversation; stop it and start it again at any time, and it carries on from the journal.

## Steps

1. **Check the controller is ready.** `orca status --json` answers, `~/.pm-runway/machines.json` lists the machines (template: `${CLAUDE_PLUGIN_ROOT}/templates/runway/machines.json`), and the repo has `runway.json` on its default branch (template beside it). If any of that is missing, point the user at the setup guide (`SETUP-AGENT.md` in the runway-agent repo) and stop.

2. **Start the chunk** from the repo root, on the default branch, after the tickets are pushed:

   ```bash
   runway start docs/maps/<effort>/tickets
   ```

   It refuses tickets that fail the readiness check or aren't `ready-for-agent`, and captures each ticket's risk and blockers in the journal (`~/.pm-runway/runs/`), so the gate never reads them from a branch a worker can touch.

3. **Run the loop in an Orca terminal tab** on the controller, so it sits beside the sessions it starts:

   ```bash
   runway loop --chunk <chunk>
   ```

   The tab redraws one status screen each tick: running or paused, the last ticket picked up and where, what is building, in review and next, and what waits on the user. Tell the user that, then end your turn: this session does not watch the loop. `runway status` shows the same screen anywhere; `runway pause` stops new work starting (running workers finish), `runway resume` lets it go again, Ctrl-C stops the loop.

4. **When the user comes back** with a question about the chunk, use `runway-ask`.

## Rules the loop keeps (so you can explain them)

- A ticket starts only when every ticket it is blocked by has **landed**, not merely been built.
- Never two tickets touching the same area at once.
- One fix pass per ticket: a failed build, a failed review, or a merge conflict sends it back once with the reason; the second failure is a needs-you.
- The reviewer is always the other model from the builder, and its verdict counts only for the commit it names.
- Workers never push to `chunk/<chunk>` or the default branch; only the loop and the gate do.
