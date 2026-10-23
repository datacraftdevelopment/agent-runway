---
name: ship-acceptance
description: Verify a deliverable against the Acceptance checks in its approved design doc and record delivery evidence. Use after implementation verification, when preparing a release, after a human deploys, or when deciding whether an intent is complete. Supports deployed systems and delivered documents or tools; never deploys production.
---

# Ship acceptance

Own the last handoff: approved design → independently executed acceptance → delivery record. A plan can finish with every task green; this procedure decides whether the design's outcome was delivered.

**In pm-runway the "intent" is the approved design doc** in `docs/specs/`, written by `brainstorming`. Its `## Acceptance` section holds the checks as `- [ ] A1: …` lines. Wherever this skill says intent, read that design doc. Older repos with `docs/intent/<slug>.md` files work the same way. Execution agreements, `dc-autonomy-v1` and Evidence requirements below come from pm's older intents; a pm-runway design doc has none of them unless it adds an `## Evidence requirements` block, so the single-evidence procedure applies by default.

## 1. Pin what will be checked

Read the approved design doc (`docs/specs/<name>.md`), the candidate's exact revision (commit or artifact SHA-256), and review dispositions. Copy the Acceptance lines verbatim with stable IDs (assign A1, A2, … in the record for legacy unnumbered lines). Record the intent file's SHA-256. Changed criteria go back to the originator under existing authorization; they are never weakened to fit output. Completion metadata is excluded from this snapshot by saving the accepted intent bytes alongside the record before later adding its completion link.

If the intent carries an `## Evidence requirements` block (acceptance ID → evidence channels: `automated`, `ui`, `state`, `human`), copy that mapping into the record **exactly** — the validator compares it against the accepted intent's digest and original criterion mapping, so a record that silently omits a UI requirement is blocked, not shipped. An intent whose approved `dc-autonomy-v1` Execution agreement lacks the block is itself blocked at validation. A legacy intent without the block keeps the original single-evidence procedure below.

Create `docs/shipped/` on first write. Use [record-template.md](./record-template.md) for `<slug>.md`; keep the accepted snapshot and `<slug>.json` beside it. Retain prior release evidence when retrying or replacing a candidate: new dated/revision sections or a new record, never overwrite a failed result with a pass.

## 2. Check the local or staging candidate

Give an evaluator who did not implement the candidate the frozen criteria, candidate identity, target, and runnable/manual procedures. For model delegation use the installed Ringer skill with an executed-check contract. Existing user authorization applies; if delegation has not been authorized, prepare the packet and offer it. A human can evaluate manual checks. The worker's own tests are supporting evidence, not this verdict.

Execute every criterion against the actual deliverable. Record per check: ID, pass/fail/not-run, exact revision, environment, evaluator identity, time, and actual output or a captured observation. Check commands and test fixtures must respect the target's permissions; a live-data write needs an explicitly approved fixture/procedure. Missing tools or access produce not-run with a reason, never an inferred pass. Review opinions do not substitute for execution.

**Multimodal criteria — when Evidence requirements name channels for a criterion:**

- Every named channel is satisfied separately, each entry carrying its own status, evaluator, timestamp, and revision. `automated` is test/script output; `ui` is actual UI interactions and captures; `state` is a persistence read through a non-UI channel (database rows, files, an API — never inferred from pixels); `human` is a recorded human check. Pixels passing while the state read fails is a failure, not a pass.
- **Builder, runner, and verifier stay separate seats** for UI evidence — the `ui-test` skill owns that pattern (instruction, receipt, fresh-context verdict). The verifier inspects the actual media (screenshots, captures), never the runner's narrative. A structurally valid PNG is not visual truth; someone independent must read it.
- Prefer the app's native or browser harness (XCUITest, Playwright) for what it covers, the computer-use pattern for what it can't reach. Fix candidate identity and the expected fixture **before** the run; cover the relevant error, empty, and recovery states, not only the happy path.
- **No automatic retries for a mutating UI case, and no concurrent GUI controllers.** Reset to a clean fixture before any re-run; a failed reset blocks every case after it.

## 3. Record readiness; let the human apply production

Failed/missing required local evidence means blocked. All required local checks pass → ready-for-release. The human applies production. Only after the human confirms deployment and the target is known, verify its actual revision and repeat the same criteria. A different revision requires fresh local evidence too.

For nondeployed deliverables, identify the actual delivered bytes and destination/use context; evaluate that artifact after delivery. A test-run copy is labeled a rehearsal, not production. Do not send files or messages to recipients without explicit authorization.

Any explicit human exception keeps the unmet check and reason visible. It can produce **released-with-exceptions**, never an unqualified shipped verdict. An exception cannot invent evidence or replace the candidate identity check. When Evidence requirements are in force, an exception must be **correctly scoped**: a required channel that is missing, not-run, or failed needs an exception naming that criterion, phase, *and* channel — a criterion-level exception does not cover a channel gap, and no exception excuses a self-evaluated channel or a wrong channel revision.

**Code-complete is not delivered.** A green suite and closed tickets prove implementation, not the intent's outcome; a criterion with a `ui` or `state` channel is undelivered until those channels hold real evidence. The agreement's `frontend_checkpoints` (typically prototype and final-demo) reserve the originator's meaningful frontend choices — an approved scope never converts those checkpoints into silent decisions.

## 4. Validate and write the shared record

The JSON companion carries `intent` (link), `intent_sha256`, `candidate`, `implementer`, `criteria` (ID → original text), and `local`/optional `delivery`. Each phase has `revision`, `environment`, and `checks`; each check has `id`, `status`, `evidence`, `evaluator`, `at`. Delivery also has `applied_by`; for a document/tool set `kind: artifact`. Exceptions are `{id, phase, approved_by, reason, at}` entries, based on the human's actual instruction.

When the intent has Evidence requirements, the record also carries `evidence_requirements` (the intent's mapping, verbatim), each covered check carries `channels` — per required channel an object with `status`, `evaluator`, `evidence`, `at`, `revision` — and a channel-scoped exception adds `channel` to the exception entry. The validator parses strictly: duplicate JSON keys, invalid types, unknown channel names, and identity mismatches all fail closed. **Every supplied channel is held to schema and identity — supplemental channels beyond the required mapping included**: a self-evaluated or wrong-revision entry blocks regardless of which channel carries it, and is never exceptable.

The intent's `## Execution agreement` and `## Evidence requirements` sections are parsed with the bundled `agreement_contract.py`, an exact byte copy of the canonical build-swarm module (parity enforced by `scripts/sync_execution_contract.py --check`). A near-miss heading — wrong case, wrong level, decorated, duplicated, or ambiguous — **blocks**; it never silently selects legacy handling. An agreement, approved or draft, must carry the full `dc-autonomy-v1` shape (policy, boolean approved, nonempty scope, known actions, technical_choices, build bounds; optional frontend/test/review fields validate when present). This validator accepts `approved: false` drafts and review-only/local-only action lists; only the build runtime additionally requires `approved: true` plus the local-edit/local-test/local-commit/ringer-build actions.

Run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/scripts/acceptance.py" --record docs/shipped/<slug>.json --intent docs/shipped/<slug>-accepted-intent.md
```

The helper validates completeness and revision/identity consistency — including that required evidence channels are present, independent, at the candidate revision, and passed or correctly excepted. It does **not** authenticate evidence or perform acceptance: it cannot tell a genuine screenshot from a staged one, or a recorded human approval from a typed-in one. Read the underlying output and confirm the criteria mapping matches the saved intent. Record the returned status in Markdown with the evidence, review dispositions and human approval. A partial release remains blocked or released-with-exceptions, with its open scope named.

For `shipped`, add `Completion: shipped · <record link>` to the current intent, after confirming its substantive content still matches the accepted snapshot. For `released-with-exceptions`, add `Completion: released-with-exceptions · <record link>` and name follow-up work; it is visible at session open until the originator accepts that tail. `ready-for-release` and `blocked` leave Completion pending. `whats-next` reads this record before excluding an intent from the frontier.

Done: shared record identifies what was requested, what was actually delivered, what was checked independently, and what remains unproven. Ship is bound by this procedure; stack-specific browser/FileMaker/API access still requires a real proving run on that stack.
