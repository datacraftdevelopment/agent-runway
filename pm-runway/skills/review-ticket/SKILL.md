---
name: review-ticket
description: "The contract for a pm-runway reviewer session that Orca started: review one ticket's exact commit, or a whole chunk branch, read-only, and report a verdict the loop can parse. Use only when the session's prompt says it is a pm-runway reviewer."
---

# Review a ticket, or a whole chunk

You were started by the pm-runway loop through Orca, as the other model from the one that built the work. You read and run; you never edit, commit, push or merge. Your verdict counts only for the commit you name, so name the one you actually reviewed.

## One ticket

1. `git fetch origin` and check out the exact commit from your prompt (detached). If `origin/rw/<ticket>` no longer points at it, say so and fail: the loop will start again from the new head.
2. Read the ticket, the spec sections its Context links, and the diff: `git diff origin/chunk/<chunk>...<sha>`.
3. Run every `Verify:` line of the ticket's Acceptance at that commit. Keep the output.
4. Judge it on three things only:
   - **Acceptance:** each line passes, by its own Verify, at this commit.
   - **Spec:** it does what the ticket and the spec say, and nothing they don't (scope creep is a finding).
   - **A lowered bar:** new skips or suppressions, deleted or weakened tests, stubs, loosened thresholds or check config. Any of these fails the ticket.
   A finding needs a file:line and the Acceptance or spec line it breaks. Style preferences are notes, not findings.
5. **Risk only rises.** Say `RISK: not-low` when the change touches something risky the ticket didn't expect (auth, money, data, migrations, CI, secrets, a public interface), even if it is correct. Otherwise repeat the ticket's risk.
6. Report with the preamble's `worker_done`, `--outcome succeeded` (the review ran, whatever the verdict), and the subject exactly `VERDICT: pass RISK: low SHA: <sha>` (or `fail`, or `not-low`). The body: each Verify result, then findings, then notes. The next builder reads your body on a fix pass, so make each finding something it can act on.

## Whole chunk

When your prompt says every ticket has landed:

1. `git fetch origin` and check out the tip of `origin/chunk/<chunk>` (detached). Note its full sha.
2. Run `pm-runway:code-review` with `origin/<base>` as the fixed point and the chunk's spec as the spec source. It reports Standards and Spec separately; keep them separate.
3. Run the spec's `## Acceptance` lines at the tip (`pm-runway:ship-acceptance`'s rules: executed checks, not readings).
4. `pass` only if every Acceptance line passed and neither axis has a hard finding. Report with `worker_done`, `--outcome succeeded`, subject exactly `VERDICT: pass SHA: <tip sha>` (or `fail`), body: Acceptance results, then `## Standards` and `## Spec`.

Skill names here are Claude Code's (`pm-runway:code-review`). A Codex reviewer has the same skills without the prefix, linked by the setup's `link-codex-skills.sh`.
