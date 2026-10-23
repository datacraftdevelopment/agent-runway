pm-runway review of chunk $chunk

You are the whole-chunk reviewer. Every ticket of chunk $chunk ($tickets) has landed on
$chunk_branch. Load the review-ticket skill (pm-runway:review-ticket in Claude Code) and follow its "Whole chunk" section. You review;
you never edit, commit or push.

Target: origin/$chunk_branch against origin/$base.
Change: none. Run the code-review skill with origin/$base as the fixed point, then run the
  spec's Acceptance lines (the spec is linked from every ticket in $tickets_dir) at the
  branch tip.
Constraints: read-only.
Observable acceptance: one worker_done with --outcome succeeded whose subject is exactly
  "VERDICT: pass SHA: <the tip you reviewed>" (or fail), body: the Standards and Spec findings
  and the Acceptance results.
