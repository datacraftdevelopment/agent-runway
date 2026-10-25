---
id: practice-01
chunk: practice
spec: docs/specs/2026-10-23-practice.md
blocked_by: []
touches: [tally/words]
risk: low
risk_reason: new standalone module in a practice repo
model: any
status: ready-for-agent
---
# Count words

## What to build
`tally.words.count_words(text)` returns how many words the text holds; words are runs of non-whitespace.

## Blocked by
None (can start immediately)

## Acceptance
- [ ] A1: `count_words("a b  c")` is 3, `count_words("")` is 0, and tabs and newlines separate words. Verify: `python3 -m unittest -q`

## Context
Spec: docs/specs/2026-10-23-practice.md, user story 1, seam `count_words`.

## Out of scope
The CLI. Line counting.
