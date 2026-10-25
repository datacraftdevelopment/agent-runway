---
name: prototype
description: "Build a quick throwaway prototype to settle one design question: how a screen should look, whether a flow or a state model feels right. Use when the person says 'prototype this', 'show me', 'mock it up', or when a question would be answered faster by seeing it than by talking about it."
---

# Prototype to answer a question

A prototype is an answer, not a start on the real thing. It is built fast to settle one question, looked at, and
thrown away. What you keep is the decision it settled.

## How

1. **Name the question** in one sentence before building anything: "Does the board read better with four columns
   or three?" If you can't name it, ask instead of building.
2. **Pick the cheapest form that answers it.**
   - Something seen (a screen, a layout, wording): one self-contained HTML file, no build step. Show two or three
     variants side by side when the question is a choice.
   - Something that behaves (a state model, a flow, an algorithm): a small script or a page with fake data that
     the person can click through or run.
3. **Fake everything else.** Hard-coded data, no persistence, no error handling, no tests. Speed is the point.
4. **Keep it out of the product.** Put it in a scratch or gitignored folder (for example `.prototypes/`), never in
   the app's source tree.
5. **Show it** (open it in the browser, or give the command to run) and ask the question again.
6. **Write the answer down** where the work continues: the map's decision file or the spec. Then offer to delete
   the prototype.

## Rules

- One question per prototype. A second question gets a second prototype.
- If the prototype starts growing into the real thing, stop and say so. The real thing gets a spec and tickets.
