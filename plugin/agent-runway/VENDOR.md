# Vendored: six skills from Superpowers

The hands-on side of Agent Runway (the `hands-on` skill) builds with six skills from Jesse Vincent's **Superpowers**
(<https://github.com/obra/superpowers>), MIT licensed. Their licence is in [`LICENSE.superpowers`](LICENSE.superpowers)
and covers these files only; the rest of Agent Runway is under the PolyForm Shield licence. The Contributor Licence
Agreement doesn't cover them: changes to them stay under MIT.

- **Upstream:** v7.0.1, commit `2ce8aa1`.
- **Copied** (git-tracked files only): `writing-plans`, `subagent-driven-development`, `executing-plans`,
  `test-driven-development`, `systematic-debugging`, `verification-before-completion`, and
  `requesting-code-review/code-reviewer.md` as `subagent-driven-development/references/code-reviewer.md` (the final
  review's template).
- **Left out:** the other Superpowers skills. Runway already does their jobs: `brainstorming` (Runway's `grill`,
  `prototype` and `spec`), `using-git-worktrees` (`runway take`), `finishing-a-development-branch` (`runway done`,
  `give`, `drop`), the code review pair (Runway's two fresh reviews). Also `systematic-debugging`'s pressure tests and
  creation log, which test the skill rather than run it.

## What was changed, and only this

1. References `superpowers:<skill>` became `agent-runway:<skill>`.
2. Skills that were left out are pointed at what replaces them: the isolated workspace is the ticket's worktree from
   `runway take`; finishing the branch is closing the ticket with the `hands-on` skill (`runway done`); the final
   review's template is the local `references/code-reviewer.md`; the `writing-skills` and `using-superpowers`
   references became plain prose or were dropped.
3. Paths: `docs/superpowers/plans/` became `docs/plans/`, and the git-ignored plan workspace `.superpowers/sdd/`
   became `.runway/sdd/`.
4. `sdd-workspace`: a comment's example path no longer spells a user folder (`C:/path/...`).

Everything else is upstream text.
