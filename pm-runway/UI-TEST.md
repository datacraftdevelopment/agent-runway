# ui-test (a skill of pm since 0.25.0)

Agent-run UI tests for any macOS app with a window — native Swift/SwiftUI apps,
FileMaker Pro, Electron — with evidence instead of claims.

**Skill:** `ui-test` — three seats that never merge. The builder (Claude Code or Codex)
writes a typed test instruction; a Codex computer-use worker runs it under Ringer
and returns a receipt (screenshots + values read off the screen, each tagged
accessibility or pixels); executed checks validate the receipt; a separate
verifier task transcribes the screenshots itself and issues the verdict.
Outcomes: `PASS-OBSERVED` / `FAIL` / `BLOCKED` — a test that could not run is
never a product failure and never a pass.

What ships:

| Path | Purpose |
|---|---|
| `skills/ui-test/SKILL.md` | the app-agnostic workflow and the rules the probe runs taught |
| `references/targets/filemaker.md`, `native-macos.md` | per-app profiles: what to approve, preconditions to state, the non-UI channel, reset, AX quirks |
| `references/tool-matrix.md` | what each seat can actually do on this stack, observed 2026-09-12; FileMaker-specific channels marked |
| `references/instruction-template.md` | the runner spec shape |
| `references/receipt-schema.md` | `truth.json`, `receipt.json`, `verdict.json` |
| `references/manifest-template.json` | two-task Ringer manifest: run, then verify |
| `scripts/check_receipt.py` | Ringer check for the run task (receipt validity) |
| `scripts/check_verdict.py` | Ringer check for the verify task (mechanical validation of a product PASS claim) |

## Assumes

- **Ringer** (see the repo README) — every runner and verifier is a Ringer task.
- **Codex computer-use approved for the target app with "always" scope**, granted
  once per app in the interactive Codex CLI. Desktop-app approvals are session-scoped and
  headless `codex exec` auto-declines the prompt.
- The target app running on the same Mac; one GUI worker at a time.
- Python 3 with Pillow in the interpreter used by both checks. Install with
  `python3 -m pip install -r '<ui-test-plugin-root>/requirements.txt'`, replacing
  the placeholder with the resolved plugin root. Missing Pillow returns a
  nonzero result with an installation command; it never falls back to headers.
- FileMaker targets: `fm-dc`'s `fm-dataapi` / `fm-otto` for data assertions and resets.

## Install

```
/plugin marketplace add datacraftdevelopment/dc-dev-plugins
/plugin install pm-runway@dc-dev-plugins
```

`ui-test` was its own plugin until pm 0.25.0. In the text below,
`<ui-test-plugin-root>` is the pm or pm-runway plugin root (the folder holding
`skills/ui-test/scripts` and `requirements.txt`).

## Evidence validation and dispatch

Both checks require a nonempty current `case_id` matching the orchestrator's
truth. A PASS requires nonempty assertions, unique assertion/artifact IDs,
artifact membership, readable PNGs that Pillow verifies and decodes, and exact
literal text matches (including whitespace). Relative evidence paths resolve
from the **receipt directory**, including when the verifier runs elsewhere.
Legacy flat observations and artifact paths without IDs remain supported.

Runner check success is receipt validation. The verifier check mechanically
validates a product PASS claim; neither script establishes that an image is an
authentic, fresh capture, depicts the claimed window, or was independently read.
The orchestrator must seed current truth and the verifier must review the actual
captures. PNG size/header tests cannot establish authenticity; the old
`min_png_bytes` field is ignored. Honest FAIL/BLOCKED reports return nonzero with
their reason even if evidence is unavailable, without claiming evidence integrity.

Before dispatch, resolve `<ui-test-plugin-root>` from the loaded skill location
and fill absolute, shell-quoted script paths in the manifest. Use the same
mechanism in Claude Code and Codex. Workers need no plugin-root environment
variable, and task directories contain case data rather than plugin runtime.

Fill the runner's `expect_files` with `receipt.json` **and every required PNG**
from `truth.artifacts_required`, plus every other planned capture used as
evidence. Match the relative paths in the receipt; list individual files, not a
directory or wildcard. The template lists all three instruction checkpoints.
Ringer harvest uses those entries: its current implementation skips files over
20 MB and flattens them to basenames, so use distinct capture filenames. Keep
the original receipt/evidence directory for replay; harvesting does not preserve
its directory structure. Missing captures on FAIL/BLOCKED can also appear as
missing `expect_files` in Ringer; retain the receipt and report that outcome.
