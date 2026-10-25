---
name: grill
description: "Interview the person about a plan, one question at a time, until every open branch of it is settled. Use when the person says 'grill me', 'stress-test this', 'poke holes in it', or when work is about to be specced and decisions are still open. Asks, never builds."
---

# Grill the plan

Work that runs unattended can't stop to ask what the person meant. Every question left open now becomes a guess
later, made by a worker with none of this conversation. This skill settles those questions while the person is here.

## How to run it

1. **Read first.** Look at what already exists before asking anything you could find out yourself: the repo, its
   docs, recent commits, any spec or map in progress. Never ask what a file can answer.
2. **List the open branches, privately.** For the plan in front of you, note each decision that isn't made yet:
   what it does, who uses it, what is out of scope, what happens at the edges (empty, too many, offline, failing),
   how anyone will know it works.
3. **Ask one question at a time.** Start with the one the most other answers hang on. Put your recommended answer
   with it, and why, so the person can just say yes. Offer two or three choices when the space is small.
4. **Follow the answer down.** Each answer opens or closes branches. Go deep on the branch you're in before you
   move on. If an answer contradicts an earlier one, say so and ask which stands.
5. **Keep a running list** of what has been decided, in a line each. Show it when it grows past five or six
   lines, and at the end.
6. **Stop when nothing is open** that would change what gets built, or when the person says enough. Anything still
   open is written down as open, never quietly assumed.

## Rules

- One question per message. A list of ten questions gets ten half answers.
- Ask about behaviour and outcomes, not implementation the person doesn't care about.
- You may push back. If an answer will cause trouble, say what trouble, once, then accept their call.
- Don't write code or files while grilling, except the decisions list if the person asks for it saved.

## After

Offer the next step: `prototype` if a question is best answered by seeing it, otherwise `spec` to write it up.
