---
name: ui-test
description: Use when a change to any macOS app with a window — a native Swift/SwiftUI app, FileMaker Pro, an Electron or Catalyst app — needs testing through its real UI rather than a headless or unit path, and the test should be run by an agent with computer use. Also use when a Codex or Claude computer-use run has returned a "done" or a screenshot and you need to decide whether it actually passed, or when a UI test could not run (wrong window, login failed, computer-use approval refused). Requires Ringer and the target app running on this Mac.
allowed-tools: Bash, Read, Write
---

# ui-test — agent-run UI tests with evidence, not claims

Three seats, never merged: the **builder** (you) writes the instruction, the
**runner** (Codex computer-use, under Ringer) performs it and returns a receipt,
the **verifier** (a fresh model context) reads the receipt and rules. The
runner's "done" is never a pass. A green Ringer check on the runner task means
*the receipt is well-formed*, not that the product works.

Nothing below depends on which app is under test. What changes per app is the
approval, the preconditions, and the non-UI channel — those live in
`references/targets/` (FileMaker Pro, native macOS). Read the matching profile.

## Workflow

1. **Split the assertions by channel.** Anything the app persists (database
   rows, files, preferences, an API) is read through that channel, never from
   pixels when one exists. Rendered state (window and view, dialog text,
   control enabled/visible, overflow markers, list rows) is the UI runner's
   job. If the app has a native UI-test harness (XCUITest, Playwright), prefer
   it for what it covers and use this pattern for what it can't reach — the
   harness choice is per-assertion, not per-app. These are the same channels
   pm's `ship-acceptance` enforces from an intent's `## Evidence requirements`
   (`ui` = this runner's interactions and captures, `state` = the persistence
   read, `automated` = harness/test output): a run here supplies those channel
   entries, and the acceptance validator blocks readiness when a required one
   is missing. Cover the relevant error, empty, and recovery states, not just
   the happy path. When a case compares the app against a reference (a
   prototype, the old app, a design), the precondition names the state both
   must be in, and the runner captures both in that state.
2. **Seed ground truth before dispatch**, independently of the runner, and
   write it to `truth.json` (`references/receipt-schema.md`) with a current,
   nonempty `case_id` that both receipt and verdict must copy exactly. Values the runner
   must read back are decided here, not after. `expected` values are literal
   strings, computed by you when writing the spec.
3. **Write the instruction** from `references/instruction-template.md`. Every
   assertion has an id, a type, an exact expected value, and the evidence that
   proves it. Preconditions state the window title, the screen or view, the
   record or fixture identity, the account. Hard rules travel in the spec.
4. **Dispatch through Ringer** with `references/manifest-template.json`:
   resolve the plugin root from this loaded skill's location in either host;
   fill absolute, shell-quoted runtime script paths before dispatch. Ensure the
   check's Python has Pillow (`<ui-test-plugin-root>/requirements.txt`). Fill
   runner `expect_files` with receipt.json and every required/planned PNG, using
   the template's harvest rules. Workers resolve evidence relative to receipt.json.
   runner task check = `scripts/check_receipt.py --truth truth.json`.
   The check fails a BLOCKED receipt on purpose so the blocker is visible;
   `max_attempts: 1` on any task whose steps mutate state.
5. **Verify in a second task** (fresh context, receipt + artifacts only, no
   runner narrative, no code): check = `scripts/check_verdict.py`. Only this
   task issues the product verdict. The script mechanically checks its PASS claim;
   authenticity, freshness, and independent transcription still require review.
6. **Reset** before any replay: relaunch the app on a clean fixture, redeploy
   the file, restore the database. Never let a retry re-run a mutating step
   against dirty state — there are **no automatic retries for mutating GUI
   cases**, by anyone: not Ringer (`max_attempts: 1`), not the runner, not
   the orchestrator deciding "once more". A failed mutating run is reported
   as it ended; a human or the builder decides whether to reset and rerun.
   The verifier rules from the receipt and the actual media (screenshots
   opened and read, values transcribed) — a structurally valid PNG is not
   visual truth, and the runner's narrative is not evidence. Candidate
   identity and the expected fixture are fixed in `truth.json` **before**
   the run, never inferred after it. Scope a visual comparison to what this
   change built: a skeleton is judged on its frame, not on content the
   reference has and the app doesn't yet.

## Outcomes

| Runner outcome | Meaning | Check result |
|---|---|---|
| `PASS-OBSERVED` | ran, every assertion has evidence and matches the runner's read | passes if values match `truth.json` |
| `FAIL` | ran, evidence contradicts an assertion | fails, prints the mismatch |
| `BLOCKED` | could not run: approval refused, window missing, login failed, evidence unreadable | fails, prints `blocker.raw_error` verbatim |
| `BLOCKED`, stage `comparison` | the app and the reference were captured in different states or sections, so nothing was compared | fails, prints the mismatch; recapture both in the named state, do not fail the product |

A BLOCKED is not a test failure of the product. Report it as its own line.

## Rules the runs taught (see `references/tool-matrix.md`)

- Codex computer-use is present in headless `codex exec` but needs a **one-time
  "always" approval per app, given in the interactive Codex CLI**. Desktop-app
  approvals are session-scoped and do not carry; the headless prompt
  auto-declines with `Computer Use was not approved to use <App>`.
- Codex reads windows through the **accessibility tree** — exact text — and
  screenshots via `app.getScreenshot()` (JPEG; convert with `sips`). The AX
  value can differ from what is rendered; the receipt must say which it
  reports (`source: accessibility | pixels`).
- Claude's own computer-use MCP reads windows fine in the background but
  **cannot type into a field the app exposes no AX write for** without
  foreground control. Use it for ground-truth seeding and reading, not driving.

## Common mistakes (each one seen in a baseline run without this skill)

- "Test the invoice screen" — no assertion ids, no expected values: unverifiable.
- "The dialog is dismissed, so its text can't be checked after the fact" — it
  can: a screenshot at the `dialog-shown` checkpoint plus a verbatim read is
  the evidence, and the verifier compares it. Dropping UI assertions because
  only data assertions have a query is dropping the reason the UI runner exists.
- Reset inside the check, with "if reset fails, don't flip the exit code."
  Reset is step 6, before the next run; a reset that fails is `BLOCKED` for
  every case after it, never a silent pass.
- Letting Ringer's default retry re-run a step that mutates state. Mutating
  lanes get `max_attempts: 1`.
- Letting the runner report a value it inferred from a screenshot as if it
  were read from the tree. Require `source` per observation.
- Treating the runner task's green check as the verdict.
- One desktop, two GUI workers. Never.
