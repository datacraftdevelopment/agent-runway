# Hands-off features: design

Status: design, 2026-10-25. Joe said yes to the four ideas from the Warp Factories review.

## Intent

Joe is one person and wants Runway to be as autonomous as possible. His judgment stays at shaping, at the go, at the risk call and at merges that aren't low risk. These four features make the hands-off part measurable, let it repair itself under review, and make it easy to step in when a ticket gets stuck. Not in scope: teams, hosting, an LLM coordinator, or a change to the merge rule.

## 1. Autonomy on the board

A small strip at the top of the board, per repo and across all repos, for the last 7 and 30 days:

- Hands-off rate: merged tickets Joe never had to do himself, divided by all merged tickets. **Ruling, 27 Oct:** answering a ticket (go or no on a question, or the Merge click on a not-low ticket) still counts as hands-off; only taking it back, doing it by hand (hands-on, counted on its own) or merging it outside Runway counts against.
- Cycle time: median time from filing to merge, shown separately for hands-off tickets and the rest.
- Cost per ticket: median, with a per-agent split. Show tokens where an agent reports no dollar cost (Codex). Never estimate.
- Where it stopped: counts of why tickets needed Joe (not low risk, review failed twice, check failed, worker question, sensitive path).

Data comes from the runs and tickets already in ~/.runway/runway.db. Add `runway stats [--json] [--repo] [--days]`, which the app reads like `status --json`. If the runs table doesn't keep the tokens and cost that Claude's JSON reports, add a migration.

## 2. Retros that open a pull request

- Trigger: 3 or more tickets in one repo stop for the same reason within 7 days, or `runway retro` is run by hand. The threshold is configurable in runway.json.
- The retro is a ticket Runway files itself. Its body lists the failing runs, each with its session line, the review text and the check output. Its job is to change the file that caused the trouble: the repo's runway.json (for example its check command), the agent-runway plugin skills, or the worker and review prompts.
- It is always not low risk, so it never merges itself. Its PR has a "Runs behind this" section that links each failure.
- No silent self-edits: Runway never changes prompts or config outside a reviewed PR.

## 3. Take back

On any open ticket (needs you, failed, running), a Take back button and `runway take <T-n>`:

- It stops the worker if one is running, marks the ticket "taken back" (this counts as not hands-off), and keeps the branch and worktree.
- It prints the line that opens a normal steered session on that branch with the ticket, the review and the failure loaded. That line is `claude --resume <id>` or `codex resume <id>` when a session exists; otherwise it is a `claude` command started in the worktree with a short brief.
- Hand back: `runway give <T-n>` (or the board button) queues it again from that branch, keeping Joe's commits.

## 4. Head-to-head

`runway bench <T-n>... [--agents claude,codex]` re-runs done tickets from their original base commit, in fresh worktrees, with each agent. It never pushes or opens a PR. It records pass or fail against the ticket's own acceptance checks and check_cmd, plus minutes, tokens and cost. The board's stats view shows a small table per agent. Routing stays manual. It runs only when Joe starts it, because it spends subscription usage.

## Order

1, then 3, then 2, then 4.

## Acceptance

- [ ] A1: With the three practice-repo tickets in the DB, `runway stats --json` reports 2 hands-off merges out of 2 merged (T-1, T-3) and one ticket waiting for Joe (T-2, not low risk), and the board strip shows the same numbers.
- [ ] A2: `runway take T-2` on a needs-you ticket prints a line that opens a session on rw/T-2. `runway give T-2` after a new commit queues it again, and the build starts from that commit.
- [ ] A3: Three tickets failing the same check within 7 days make Runway file one not-low retro ticket whose PR links all three runs. It does not merge itself.
- [ ] A4: `runway bench T-1 --agents claude,codex` produces two results with pass or fail, minutes and cost, and pushes no branch.
