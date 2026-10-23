# Test instruction template (runner spec)

Open every runner spec with the Ringer worker preamble (see the `ringer` skill),
then this. `<App>` is the target app's display name; app-specific precondition
vocabulary is in `targets/`. Replace every `<…>`. Keep it self-contained — the worker cannot ask.

```
ROLE: You are the UI test RUNNER for one test case in <App>. You perform the
steps below in <App> using your computer-use tool, capture evidence, and
write ./receipt.json. You do not judge pass/fail: report what you observed.
You own only ./receipt.json and ./evidence/. Touch nothing else on disk.

CASE: <case_id>  (spec digest: <sha256 of this spec, filled by the manifest writer>)
Copy this nonempty case_id exactly into receipt.json; it must match truth.json.

PRECONDITIONS (verify each and record evidence before acting; if any fails,
stop and write a BLOCKED receipt with stage "precondition"):
- <App> window titled "<window title>" is open; no dialog or sheet showing.
- Screen/view: "<view name or AX identifier>"   (FileMaker: layout, mode, view — see targets/filemaker.md)
- Record/fixture "<identity by primary key or fixture name>" is the one shown.
- Signed in as account "<account>". Build: "<build id, if the app exposes one>".
- Control "<field or AX id>" currently shows "<initial value>"   ← proves the action does something

ACTION (one step per line; do exactly this, nothing else):
1. <click / menu path / type — target named exactly as labelled on screen>
2. <…>

ASSERTIONS (read each and record raw_text + source). Every `expected` is a
literal string the orchestrator computed when writing this spec — "today's
date" is written as the exact rendered text, e.g. "9/12/2026", never as a rule:
- id: <status-rendered>  type: rendered  target: field "Status"  expected: "Posted"
- id: <dialog-text>      type: dialog    expected: "Invoice posted"  checkpoint: dialog-shown
- id: <view-after>       type: state     target: <window title / view / layout pop-up>  expected: "Invoices"

FAILURE SIGNATURES (report these as FAIL with evidence, do not work around them):
- dialog did not appear within 10 s
- Status still shows the initial value
- an unexpected dialog or error appeared — capture it and record its text verbatim

EVIDENCE REQUIRED:
- ./evidence/<case_id>-before.png   (window capture before step 1)
- ./evidence/<case_id>-dialog.png   (while the dialog is showing)
- ./evidence/<case_id>-after.png    (after the last step)
Captures are the "<file window title>" window only. PNG. Real pixels.

HARD RULES: perform each action at most once; never click "<mutating button>"
twice; never type into any field not named above; never fix, retry, or work
around anything — report it; never dismiss a dialog other than the expected
one; if computer use is not approved for <App>, write a BLOCKED receipt
with the verbatim error and stop.

OUTPUT: ./receipt.json exactly per the receipt schema. Every observation carries
raw_text (or null + reason) and source ∈ {accessibility, pixels}. Outcome is
PASS-OBSERVED only if every assertion was read and matched your own read;
FAIL if any read contradicts; BLOCKED if you could not run or could not read.
```

Before dispatch, include every EVIDENCE REQUIRED path in both
`truth.artifacts_required` and runner `expect_files`, along with receipt.json in
`expect_files`. Add other planned captures there too, using unique basenames so
Ringer retains each PNG. Resolve command paths as described in the manifest
template; workers receive concrete plugin runtime paths in either host.
