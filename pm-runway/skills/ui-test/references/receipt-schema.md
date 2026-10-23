# truth.json, receipt.json, verdict.json

## truth.json — written by the orchestrator BEFORE dispatch

```json
{
  "case_id": "invoice-post",
  "spec_sha256": "…",
  "assertions": {
    "status-rendered": {"expected": "Posted", "type": "rendered"},
    "dialog-text":     {"expected": "Invoice posted", "type": "dialog", "checkpoint": "dialog-shown"},
    "view-after":    {"expected": "Invoices", "type": "state"}
  },
  "artifacts_required": ["evidence/invoice-post-before.png", "evidence/invoice-post-dialog.png", "evidence/invoice-post-after.png"],
  "data_assertions": {"Invoices.Status where pk=1042": "Posted"}
}
```
`data_assertions` are checked by the orchestrator through the app's non-UI channel (Data API, SQLite, defaults, API), not by the runner, and not by either script — so they may be relational (`> baseline`, `within 2s of now`) where UI `assertions` must be literal strings.

For each dispatch, the orchestrator supplies a current, nonempty string
`case_id`; copy it exactly into receipt and verdict. The scripts enforce matching
IDs, not freshness by themselves. PASS requires at least one assertion. Expected
and observed values are strings compared literally, including whitespace.
Duplicate JSON keys (including assertion IDs) are rejected rather than overwritten.
`min_png_bytes` is obsolete and ignored: byte count does not establish authenticity.

When a run feeds a pm `ship-acceptance` record with `## Evidence requirements`,
the mapping is: UI `assertions` proven by the runner's interactions and
captures → the `ui` channel; `data_assertions` read through the non-UI
channel → the `state` channel; native-harness/test output → `automated`.
Each channel entry in the acceptance record carries its own evaluator,
timestamp, and revision — the runner's identity never evaluates its own work.

## receipt.json — written by the runner

```json
{
  "schema_version": "1",
  "case_id": "invoice-post",
  "execution_outcome": "PASS-OBSERVED | FAIL | BLOCKED",
  "tool_used": "<exact tool / function names>",
  "read_method": "accessibility | pixels | mixed",
  "preconditions": [{"id": "current-record", "held": true, "evidence_ref": "a0"}],
  "actions": [{"seq": 1, "target": "Post button", "operation": "click", "performed_at": "UTC ISO"}],
  "observations": {
    "status-rendered": {"raw_text": "Posted", "source": "accessibility", "artifact_ref": "a2"},
    "dialog-text":     {"raw_text": "Invoice posted", "source": "accessibility", "artifact_ref": "a1"},
    "view-after":    {"raw_text": "Invoices", "source": "accessibility", "artifact_ref": "a2"},
    "unreadable-example": {"raw_text": null, "source": "pixels", "reason": "field occluded by dialog", "artifact_ref": "a1"}
  },
  "artifacts": [
    {"id": "a0", "path": "evidence/invoice-post-before.png", "checkpoint": "before", "captured_at": "UTC ISO", "window_title": "Invoices"},
    {"id": "a1", "path": "evidence/invoice-post-dialog.png", "checkpoint": "dialog-shown", "captured_at": "…", "window_title": "Invoices"},
    {"id": "a2", "path": "evidence/invoice-post-after.png",  "checkpoint": "after", "captured_at": "…", "window_title": "Invoices"}
  ],
  "unexpected": [{"kind": "dialog", "raw_text": "…verbatim…", "artifact_ref": "a2"}],
  "mutations_made": false,
  "notes": "anything the tool said, verbatim",
  "blocker": {"stage": "precondition | locate_app | action | evidence | comparison", "code": "COMPUTER_USE_NOT_APPROVED | WINDOW_NOT_FOUND | LOGIN_FAILED | EVIDENCE_UNREADABLE | STATE_MISMATCH | …", "reason": "…", "raw_error": "…verbatim…", "last_completed_action": 0}
}
```
`observations` may also be flat `{"id": "raw text"}` — `check_receipt.py` accepts both.

For PASS, `artifacts` must be nonempty, contain every `artifacts_required` path,
and list only readable images that Pillow verifies and decodes as PNG. Relative
paths resolve against the receipt's directory, not the check's working directory.
Artifact paths must be unique. IDs are optional for legacy path-only receipts;
when present they must be nonempty and unique, and may not ambiguously name a
different artifact's path. Every supplied observation `artifact_ref` and every
verifier row's required `artifact_ref` must name a listed artifact ID or path.
The same membership rule applies to supplied precondition `evidence_ref` and
unexpected-event `artifact_ref` values.
Keep every planned PNG in the runner manifest's `expect_files` for harvest;
see `manifest-template.json` for fill-in rules and retention limits.

## verdict.json — written by the verifier

```json
{
  "case_id": "invoice-post",
  "verdict": "PASS | FAIL | BLOCKED",
  "per_assertion": [
    {"id": "status-rendered", "expected": "Posted", "observed_by_verifier": "Posted", "artifact_ref": "a2", "result": "pass"},
    {"id": "dialog-text", "expected": "Invoice posted", "observed_by_verifier": "Invoice posted.", "artifact_ref": "a1", "result": "fail", "note": "trailing period on screen"}
  ],
  "runner_disagreements": ["dialog-text: runner read 'Invoice posted', screenshot shows 'Invoice posted.'"],
  "basis": "screenshots and receipt values only; runner notes not used"
}
```
The verifier transcribes each artifact itself. `verdict` may be PASS only when every
`per_assertion.result` is `pass` and no assertion is missing. Row IDs must be
unique and belong to truth. The check first validates the full PASS-OBSERVED
receipt contract, including image decoding, literal reads, and mutation policy.
A runner FAIL or BLOCKED cannot become a product PASS.

For honest FAIL/BLOCKED, missing evidence or assertion rows alone are not a
malformed receipt/verdict. Include the reason in `blocker`/`notes` on the receipt
and `basis` on the verdict. These outcomes always return nonzero and print the
reason; case IDs still must match. A negative verdict may report that no receipt
was available. No evidence-integrity claim is made for these incomplete reports.

An exit 0 from `check_receipt.py` is runner check success. An exit 0 from
`check_verdict.py` is mechanical validation of the verifier's product PASS
claim. Neither proves capture authenticity, freshness, or independent transcription.
