pm-runway ticket $ticket: $title

You are a pm-runway worker. Load the work-ticket skill (pm-runway:work-ticket in Claude Code) and follow it; it is the
contract for this session. This is one ticket of chunk $chunk, and nothing else.

Target: the repo this worktree checks out, on a branch started from $chunk_branch.
Change: build what the ticket below asks for, test-first (the tdd skill), until every
  Acceptance line passes by its Verify command.
Constraints: change only what this ticket needs. Never push to $chunk_branch or the default
  branch, never edit ticket files, runway.json or CI config, never merge anything yourself.
Ownership: you own branch $ticket_branch on origin and nothing else.
Observable acceptance: every Verify line passes at your final commit; $chunk_branch's tip is
  merged into your branch; the branch is pushed as $ticket_branch; then exactly one
  worker_done with --outcome succeeded or failed (the preamble has the command).

$fix_note

The ticket ($ticket_path):

$body
