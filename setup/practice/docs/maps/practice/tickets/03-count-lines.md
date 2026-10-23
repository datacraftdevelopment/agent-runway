---
id: practice-03
chunk: practice
spec: docs/specs/2026-10-23-practice.md
blocked_by: []
touches: [tally/lines]
risk: low
risk_reason: new standalone module in a practice repo
model: any
status: ready-for-agent
---
# Count lines

## What to build
`tally.lines.count_lines(text)` returns how many lines the text holds: a final line without a newline still counts, and empty text is 0.

## Blocked by
None (can start immediately)

## Acceptance
- [ ] A1: `count_lines("x\ny")` is 2, `count_lines("x\n")` is 1, `count_lines("")` is 0. Verify: `python3 -m unittest -q`

## Context
Spec: docs/specs/2026-10-23-practice.md, user story 2, seam `count_lines`.

## Out of scope
The CLI. Word counting.
