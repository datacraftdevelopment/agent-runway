# Lanes and risk tiers (pm-runway)

Part of pm-runway:subagent-driven-development. Both come from the plan:
writing-plans adds the `## Lanes` section and a `**Risk:**` line per task.

## Lanes

**Lanes run at the same time** (pm-runway). When the plan has a `## Lanes`
section, don't wait for one lane to finish before starting the next.

1. **Set each lane up once,** when the task it waits for is complete: a
   branch cut from the plan's branch and a worktree for it, made with
   pm-runway:using-git-worktrees (the manual path, under
   `.superpowers/worktrees/<plan>-<lane>`). Not the Agent tool's per-dispatch
   worktree isolation: that cuts a fresh worktree from your HEAD for every
   dispatch, so a lane's second task would never see its first. Write
   `Lane <name>: worktree <path>, branch <branch>, base <sha>` to the ledger.
2. **Dispatch lanes side by side.** Each implementer's dispatch names its
   lane's worktree as the directory it works in. Tasks inside a lane still
   run one after another. Three implementers at once is the ceiling.
3. **Keep one workspace.** Run `scripts/review-package` and every other
   script from the plan's own worktree root, with the lane's BASE and HEAD
   commits (worktrees share one object store), so the ledger, briefs and
   packages stay in the plan's workspace. BASE is per lane.
4. **Ledger lines** carry the lane:
   `Task <N> [lane <name>]: complete (commits <base7>..<head7>, …)`, so
   resuming still finds every `Task <N>` … `complete` line.
5. **Merge a finished lane** into the plan's branch, run the tests there,
   and only then start a task that waits on it. This merge stays inside the
   plan's own branch, so it is not one of the merges you stop and ask about;
   merging the plan's branch anywhere else still is.

A plan with no Lanes section runs one task at a time; if you can see
disjoint tasks it missed, rule them into lanes in the ledger and run them
the same way.

## Risk tiers

**Scaled by risk** (pm-runway). The plan tags each task `**Risk:**`. A **high**
task gets SKILL.md's task review, every time. An **ordinary** or **low**
task skips it: the implementer's tests and self-review stand, and the
whole-branch review at the end covers it, with every ordinary and low task
named in that review's brief. A task with no Risk line is high. If an
implementer's report shows the task touched data correctness, security or
an external contract after all, raise it to high and review it. Ledger
line: `Task <N>: complete (commits <base7>..<head7>, risk <tier>, no task
review)`.

## Screens

A task that builds or changes a screen (pm-runway) isn't complete until its
screenshots, every view it touches on real data at a real window size, are
in the plan's workspace and match the approved screens. Reviews read code;
only a look catches a broken layout.
