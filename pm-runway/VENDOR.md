# Vendored: pm-sp, and through it Superpowers and Matt Pocock's skills

pm-runway carries everything it uses, so a pm-runway machine installs no other workflow plugin. Never install it alongside `pm-sp`, `pm`, upstream Superpowers or `mattpocock-skills`: they share skill names, and two copies of the credential guard would both run.

## pm-sp

All of pm-sp (from `datacraftdevelopment/dc-dev-plugins`, folder `pm-sp/`), which itself vendors a trimmed Superpowers and seven of Matt Pocock's skills. Its own record of those, with every change it made, is kept below under "pm-sp's own record".

- **Upstream:** dc-dev-plugins commit `4783a24` (pm-sp 0.2.6, 2026-10-22).
- **Copied by** `scripts/sync_vendor.py` (git-tracked files only, via `git archive`), every `pm-sp` renamed `pm-runway`. Re-running the script with the same commits gives the same tree.
- **Kept as pm-runway's own** (the script never overwrites these): `.claude-plugin/plugin.json`, `README.md`, this file, and the two files changed below.

### What was changed, and only this

1. `skills/second-opinion/SKILL.md`: Ringer is optional. With Ringer, Sol is one Ringer task as before; without it, Sol is `codex exec --sandbox read-only` with the same packet; without Codex, Opus alone, marked as such.
2. `template/docs/agents/issue-tracker.md`: a "Build tickets" section for `docs/maps/<effort>/tickets/`, beside wayfinder's decision tickets.
3. `skills/brainstorming/SKILL.md` (applied by the script, see `EDITS`): after an approved design, ask whether to plan it by hand (`writing-plans`) or cut it into tickets for the loop (`to-spec`, then `to-tickets`); ticketed work has no plan document.

Search the copied tree for `pm-runway:` notes to see each change in place.

## Matt Pocock's skills

From **mattpocock/skills** (<https://github.com/mattpocock/skills>), MIT (`LICENSE.mattpocock`), commit `5beb35b` (2026-10-19, release 1.3.1), the same commit pm-sp vendors from.

### Verbatim (synced by the script)

- `tdd` (with `tests.md`, `mocking.md`) and `code-review`, without the Codex `agents/openai.yaml` cards. One edit: `code-review`'s missing-tracker hint points at `docs/agents/issue-tracker.md` instead of `/setup-matt-pocock-skills`.
- `tdd` sits beside Superpowers' `test-driven-development` on purpose: the hand-run flow (writing-plans, subagent-driven-development) keeps Superpowers' skill, and ticket workers use Matt's, whose seam rule matches the spec's agreed test seams.

### Ours, derived from his (merged by hand on a re-sync)

Each keeps his text where it still applies, marks every change `pm-runway:` in place, and names his commit in a comment at the top.

- `to-spec`: writes `docs/specs/YYYY-MM-DD-<chunk>.md` instead of publishing an issue; adds the chunk's risk (step 3), a `## Acceptance` section, and the agreed test seams in Testing Decisions; offers `to-tickets` after.
- `to-tickets`: local files in `docs/maps/<effort>/tickets/` with the pm-runway header (`touches`, `risk`, `model`, `status`), a `Verify:` on every Acceptance line, `runway check` before filing, `status: ready-for-agent` and a commit only on the user's go. The quiz also asks about risk and work a person should do. Vertical-slice and expand-contract rules unchanged.
- `implement-spec`: his steps are kept; who does each changed. A plain loop script and fresh Orca workers on several machines replace the one session with background subagents; review by the other model before each merge; the gate replaces "mark the PR ready".

### Ours, new

`work-ticket`, `review-ticket`, `runway-ask`, the `runway/` CLI, `bin/runway`, `templates/runway/`, `RUNWAY.md`. Ideas borrowed, not text: the ticket readiness rules (Spec Kit, Kiro, Task Master, BMAD, Beads, Symphony, GitHub's Copilot guidance), and from Nate Jones' Open Engine the two kinds of pause (a question vs a hold) and the failed worker's last safe step.

## Updating

Roughly monthly, or when an upstream release matters:

1. Pull dc-dev-plugins and mattpocock/skills.
2. `python3 scripts/sync_vendor.py --pm-sp <dc-dev-plugins>/pm-sp --matt <mattpocock-skills>` from the runway-agent root. It stops if one of its edits no longer matches.
3. Diff Matt's `to-spec`, `to-tickets` and `implement-spec` against `5beb35b` and bring what changed into ours by hand. Check `second-opinion` and `issue-tracker.md` against pm-sp's versions the same way.
4. Update the commits above, bump `version` in `.claude-plugin/plugin.json`, run `python3 -m unittest discover -s tests`.

---

## pm-sp's own record

The rest of this file is pm-sp's `VENDOR.md` at the commit above, unchanged except for the rename.

## Vendored: Superpowers and Matt Pocock's skills

pm-runway carries what it uses from two outside packs, so a pm-runway machine installs
no other plugin. Each copy is upstream text except the changes listed, and
each change is marked `pm-runway` in place.

### Superpowers

pm-runway carries a trimmed copy of Jesse Vincent's **Superpowers**
(<https://github.com/obra/superpowers>), MIT licensed (`LICENSE.superpowers`).

- **Upstream:** v7.0.1, commit `2ce8aa1` (2026-10-21).
- **Copied** (git-tracked files only, via `git archive`): `brainstorming`,
  `writing-plans`, `subagent-driven-development`, `executing-plans`,
  `finishing-a-development-branch`, `using-git-worktrees`,
  `requesting-code-review`, `receiving-code-review`, `test-driven-development`,
  `systematic-debugging`, `verification-before-completion`,
  `dispatching-parallel-agents`.
- **Left out:** `using-superpowers` and the SessionStart hook that injects it
  (the "even a 1% chance, you MUST invoke a skill" rule that takes over every
  session), `writing-skills`, `diagnosing-superpowers`, and
  `systematic-debugging`'s pressure-test and creation-log files (they test the
  skill, they don't run it).

#### What was changed, and only this

1. Cross-references `superpowers:<skill>` became `pm-runway:<skill>`; the one
   reference to `writing-skills` became plain prose; `executing-plans` no
   longer points at `using-superpowers/references/`.
2. Paths: `docs/superpowers/specs/` → `docs/specs/`, `docs/superpowers/plans/`
   → `docs/plans/`. The gitignored working directory `.superpowers/` (ledgers,
   review packages, mockups) is unchanged, to keep upstream merges easy.
3. `brainstorming`: a calmer description (no "You MUST use this before any
   creative work"); the design doc gains an `## Acceptance` section in the
   `- [ ] A1: …` form `ship-acceptance` reads; a pm-runway second-opinion step after
   the builder check; and after the design is approved it **asks** whether to
   plan now instead of going straight to `writing-plans`.
4. `writing-plans`: an optional `## Lanes` section for `nested-sessions`.
5. `finishing-a-development-branch`: Step 1b, a pm-runway second-opinion on the
   branch before the options.
6. Models named at every dispatch: `subagent-driven-development`'s tier map
   (sonnet / opus, never fable or haiku), `executing-plans`' final review,
   brainstorming's builder check, `dispatching-parallel-agents`,
   `requesting-code-review`.
7. Script paths: both executors say their `scripts/` mean
   `${CLAUDE_PLUGIN_ROOT}/skills/.../scripts/`, run from the project worktree.
8. `finishing-a-development-branch`: Step 7 offers ship-acceptance and
   stepping-away. `brainstorming`'s opening checklist asks before planning.

Everything else is upstream text. Search for `pm-runway` in the copied skills to
see each change in place.

### Matt Pocock's skills

From **mattpocock/skills** (<https://github.com/mattpocock/skills>), MIT
licensed (`LICENSE.mattpocock`).

- **Upstream:** commit `5beb35b` (2026-10-19); the seven skills are identical
  to release 1.3.1.
- **Copied** (git-tracked files only, without the Codex `agents/openai.yaml`
  files): `wayfinder`, `grilling`, `domain-modeling`, `codebase-design`,
  `prototype`, `research`, `pr` (with its `CREDITS.md`, which credits Dex
  Horthy's `show-me`). `templates/issue-tracker-github.md` is his
  `setup-matt-pocock-skills` GitHub tracker doc, without its PR-triage
  section.
- **Left out:** the ticket-per-session flow (`to-spec`, `to-tickets`,
  `implement`, `implement-spec`, `triage`), the parts Superpowers already
  covers (`tdd`, `diagnosing-bugs`, `code-review`), `grill-me`, `handoff`,
  `retro`, `setup-matt-pocock-skills` and the rest.

#### What was changed, and only this

1. `wayfinder`: the missing-tracker hint points at `/pm-runway:scaffold`; a
   paragraph makes pm-runway's usual destination a set of chunks in order, each
   brainstormed in its own session; and a session may take the next ticket
   after recording the last, instead of one ticket per session; research
   findings go where the tracker doc says (pm-runway's local tracker keeps maps,
   tickets and research in `docs/maps/<effort>/`), not on a throwaway branch.
2. `prototype`: the decision is recorded in the design doc or wayfinder
   ticket; all prototype code goes to a throwaway branch, never into the
   product (the plan writes the real code).
3. `wayfinder` drops `disable-model-invocation`, so naming it ("use
   wayfinder") starts it, and its description says to run only when named.
   Map Notes can no longer authorize implementation.
4. `research` and `codebase-design`'s design-it-twice name their models.

### The visual companion

Brainstorming's browser companion (`skills/brainstorming/scripts/`) runs a
small local server. Its page loads the Superpowers logo from primeradiant.com,
which tells the author which version is in use and nothing about the project.
Set `SUPERPOWERS_DISABLE_TELEMETRY=1` (or Claude Code's `DISABLE_TELEMETRY`) to
turn that off. It needs a local browser, so it works on the Mac and not in a
cloud session.

### Updating from upstream

Roughly monthly, or when a release note matters:

1. Clone each upstream at its new release and diff its copies of the skills
   above against the previously vendored commit.
2. Apply upstream changes here, keeping the changes listed above.
3. Update the commit line at the top, bump pm-runway's version, run
   `python3 -m pytest tests/test_pm_sp_plugin.py -q` from the marketplace root.
