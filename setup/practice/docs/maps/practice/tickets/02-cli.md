---
id: practice-02
chunk: practice
spec: docs/specs/2026-10-23-practice.md
blocked_by: [practice-01, practice-03]
touches: [tally/cli]
risk: low
risk_reason: a CLI entry point in a practice repo
model: any
status: ready-for-agent
---
# Print counts from the command line

## What to build
`python3 -m tally <file>` prints `words: N` then `lines: N`, using `count_words` and `count_lines`. A missing file exits 2 with a message on stderr.

## Blocked by
- practice-01 Count words
- practice-03 Count lines

## Acceptance
- [ ] A1: On a file holding "one two three", it prints `words: 3` then `lines: 1` and exits 0. Verify: `python3 -m unittest -q` (a test that runs the CLI as a subprocess)
- [ ] A2: A missing file exits 2 and prints to stderr. Verify: `python3 -m unittest -q`

## Context
Spec: docs/specs/2026-10-23-practice.md, user stories 1 to 3, seam: the CLI as a subprocess.

## Out of scope
Several files, flags.
