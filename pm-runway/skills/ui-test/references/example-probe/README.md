# Worked example — the 2026-09-12 capability probe

The first real run of this pattern (FileMaker Pro target; see `targets/filemaker.md`): one Codex computer-use task under Ringer,
asked to capture the FileMaker Pro window "ProbeFile" and read ten on-screen
values, checked against values the orchestrator had seen on the same screen.

- `manifest.json` — the one-task manifest (spec, check, `verified`), paths scrubbed.
- `truth.json` — the orchestrator's ground truth in `check_receipt.py` form.
- `receipt.json` — the runner's receipt (PASS-OBSERVED, attempt 1, 21k tokens, 74 s),
  adapted with the matching `case_id` now required by the checks; observations
  and capture metadata are preserved.
  Read `notes`: it records that the AX tree exposed `ID` as `6.1412E+57` and
  `fk_XXX_ID` as `PROBE-7Q4M-2026` while both *render* as `?`, that the capture
  tool returned JPEG and was converted with `sips`, and the verbatim tool errors
  hit on the way — the kind of receipt the contract wants.

Two earlier attempts of the same manifest returned honest `BLOCKED` receipts
(`Computer Use was not approved to use FileMaker Pro`) until FileMaker Pro was
approved with "always" scope in the interactive Codex CLI.

The historical capture is not bundled, so these JSON files alone cannot pass
the current checker. PNG decode establishes format integrity, not authenticity.
The example is a runner probe; it contains no independent product verdict.

Replay: open a copy of `fm-dc/tests/patch/fixtures/dev.fmp12` as `ProbeFile.fmp12`,
create one record, re-seed `truth.json` from what you see with a fresh case_id,
and update the manifest spec to match. Resolve `<ui-test-plugin-root>` from the
loaded skill in either host; fill the check's absolute, shell-quoted paths and
place truth.json at the specified location. `expect_files` includes the capture
so it is harvested alongside the receipt. Then run
`ringer lint manifest.json && ringer run manifest.json`.
