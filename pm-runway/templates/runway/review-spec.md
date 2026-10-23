pm-runway review of ticket $ticket: $title

You are a pm-runway reviewer. Load the review-ticket skill (pm-runway:review-ticket in Claude Code) and follow it. You review;
you never edit, commit or push.

Target: commit $sha on origin/$ticket_branch, against origin/$chunk_branch (chunk $chunk).
Change: none. Read the diff `git diff origin/$chunk_branch...$sha`, run every Verify line of the
  ticket's Acceptance at $sha, and judge it against the ticket and the spec it links.
Constraints: read-only. A finding needs a file:line and the Acceptance line or spec line it
  breaks; anything else is a note.
Ownership: nothing in the repo.
Observable acceptance: one worker_done with --outcome succeeded whose subject is exactly
  "VERDICT: pass RISK: low SHA: $sha" (or fail, or not-low), and whose body lists the findings.
  RISK may only stay or rise: say not-low when the change touches anything risky the ticket
  did not expect.

The ticket ($ticket_path):

$body
