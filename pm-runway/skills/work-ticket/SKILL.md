---
name: work-ticket
description: "The contract for a pm-runway worker session that Orca started for one ticket: build it test-first on its own branch, merge the chunk tip in, push, and report once with worker_done. Use only when the session's prompt says it is a pm-runway worker and carries an Orca task and dispatch id."
---

# Work one ticket

You were started by the pm-runway loop through Orca, for one ticket. Nobody is watching this session. Your prompt holds the ticket, the chunk branch and your branch name, and Orca's preamble holds your task id, dispatch id and the exact commands for `ask` and `worker_done`. The preamble is authoritative for Orca's commands; this skill is authoritative for the work.

## The work

1. **Start from the chunk.** Confirm your worktree is based on `origin/chunk/<chunk>` (`git merge-base --is-ancestor origin/chunk/<chunk> HEAD`). If not, `git fetch origin` and reset onto it. On a fix pass your prompt says so: start from `origin/rw/<ticket>` instead and read what went wrong last time first.
2. **Read, don't re-plan the chunk.** Read the ticket, then the spec sections and test seams its Context links, `GLOSSARY.md` and the ADRs in the area. Plan this one ticket inside this session; there is no plan document.
3. **Build it test-first** with the `pm-runway:tdd` skill, at the seams the spec agreed. One Acceptance line at a time.
4. **Run every `Verify:` line** of the ticket's Acceptance yourself and keep the output. A line you cannot run here (it needs something this machine lacks) is a failure to report, not a line to skip.
5. **Merge the chunk tip in** before you finish: `git fetch origin && git merge origin/chunk/<chunk>`. Resolve conflicts in favour of what is already on the chunk branch plus your ticket; rerun the Verify lines after.
6. **Push your branch, and only it:** `git push origin HEAD:refs/heads/rw/<ticket>` (force-with-lease on a fix pass if you rebased). The loop reads your commit from origin, not from your report.
7. **Report once** with the preamble's `worker_done` command: `--outcome succeeded` only when every Verify line passed at the pushed commit, otherwise `--outcome failed`. Summary: what you built, the Verify results, anything left. On a failure, also the **last safe step**: the last commit where things were good and what the fix pass should do first (the next builder starts from it). Then stop and idle.

## Never

- Edit ticket files, `runway.json`, CI config, or anything the ticket's Out of scope names.
- Push to `chunk/<chunk>` or the default branch, merge a PR, or start other tickets.
- Weaken a test, skip one, or loosen a check to get green. A red you can't fix is `--outcome failed` with the reason.
- Open a local question prompt. If you are truly blocked on a decision, use the preamble's `ask` command once with a crisp question; the user answers through Orca. Otherwise make the call, say why in your summary, and carry on.

Skill names here are Claude Code's (`pm-runway:tdd`). A Codex worker has the same skills without the prefix (`tdd`), linked by the setup's `link-codex-skills.sh`.
