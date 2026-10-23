---
name: to-spec
description: "Write a chunk's spec from what has already been talked through, in Matt Pocock's to-spec shape plus pm-runway's Acceptance lines, as a file in docs/specs/. No interview, just synthesis. Use after brainstorming (or a wayfinder chunk) when the work is headed for tickets and the loop, or when the user says \"write the spec\", \"to-spec\", \"spec this chunk\"."
disable-model-invocation: true
---

<!-- pm-runway: our version of Matt Pocock's to-spec (mattpocock/skills 5beb35b). Changes are listed in VENDOR.md and marked "pm-runway" below. -->

This skill takes the current conversation context and codebase understanding and produces a spec. Do NOT interview the user; just synthesize what you already know.

pm-runway: the spec is a file, `docs/specs/YYYY-MM-DD-<chunk>.md`, committed on the default branch, never an issue. `<chunk>` is a short slug (`inbox-v2`); every ticket cut from this spec carries it. If the talk came out of a wayfinder map, the chunk is one of its numbered chunks: link the map.

## Process

1. Explore the repo to understand the current state of the codebase, if you haven't already. Use the project's domain glossary vocabulary throughout the spec, and respect any ADRs in the area you're touching.

2. Sketch out the seams at which you're going to test the feature. Existing seams should be preferred to new ones. Use the highest seam possible. If new seams are needed, propose them at the highest point you can. The fewer seams across the codebase, the better - the ideal number is one.

Check with the user that these seams match their expectations.

3. pm-runway: settle the chunk's **risk** with the user in one line: `low` (a reason it can't hurt anything that matters: copy, a new isolated screen, tests only) or `not-low` (anything touching auth, money, data, migrations, CI, or that you can't explain away in one line). Only a low chunk can reach the default branch without the user. Reviewers can raise it later, never lower it.

4. Write the spec using the template below and commit it (`docs: spec for <chunk>`). pm-runway: then offer `to-tickets`; never cut tickets before the user has seen the spec.

<spec-template>

# <Chunk title>

Chunk: <chunk-slug> · Risk: <low: reason | not-low> · Map: <docs/maps/<effort>/map.md, or none>

## Problem Statement

The problem that the user is facing, from the user's perspective.

## Solution

The solution to the problem, from the user's perspective.

## User Stories

A LONG, numbered list of user stories. Each user story should be in the format of:

1. As an <actor>, I want a <feature>, so that <benefit>

<user-story-example>
1. As a mobile bank customer, I want to see balance on my accounts, so that I can make better informed decisions about my spending
</user-story-example>

This list of user stories should be extremely extensive and cover all aspects of the feature.

## Implementation Decisions

A list of implementation decisions that were made. This can include:

- The modules that will be built/modified
- The interfaces of those modules that will be modified
- Technical clarifications from the developer
- Architectural decisions
- Schema changes
- API contracts
- Specific interactions

Do NOT include specific file paths or code snippets. They may end up being outdated very quickly.

Exception: if a prototype produced a snippet that encodes a decision more precisely than prose can (state machine, reducer, schema, type shape), inline it within the relevant decision and note briefly that it came from a prototype. Trim to the decision-rich parts, not a working demo, just the important bits.

## Testing Decisions

A list of testing decisions that were made. Include:

- A description of what makes a good test (only test external behavior, not implementation details)
- Which modules will be tested
- The agreed test seams (pm-runway: workers test only at these)
- Prior art for the tests (i.e. similar types of tests in the codebase)

## Acceptance

pm-runway: three or four observable checks for the whole chunk, each with how to verify it. The whole-chunk review and `ship-acceptance` run these against the chunk branch.

- [ ] A1: <what a person or a test can observe>. Verify: <a command or a short manual procedure>

## Out of Scope

A description of the things that are out of scope for this spec.

## Further Notes

Any further notes about the feature.

</spec-template>
