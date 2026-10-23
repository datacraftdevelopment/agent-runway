# Tool matrix — what each seat can actually do (observed 2026-09-12)

The pattern is app-agnostic: the runner, receipt, checks and verifier never
change. Rows marked *(FileMaker)* are the app-specific channels for that target;
see `targets/` for others. Every row was exercised on this Mac against a
FileMaker Pro 2025 client with a local test file open, unless marked "not yet". "Observed" means it happened in a Ringer run or an
orchestrator session; "not yet" means untested here.

| Tool | Reads rendered state | Reads exact values | Screenshots | Drives the UI | Reset / seed | Unattended? |
|---|---|---|---|---|---|---|
| **Codex computer-use** (`unified-computer-use` plugin, reached through `codex exec` under Ringer) | yes — accessibility tree of the window, incl. layout pop-up and toolbar record count | yes — AX values are exact text; note the AX value can be the *stored* value (`6.1412E+57`, `PROBE-7Q4M-2026`) while the field *renders* `?` — receipt must say which | `app.getScreenshot()` returns JPEG; worker converts with `sips -s format png` | yes — clicked through layouts in the interactive CLI; headless driving not yet exercised | no | **only after a one-time "always" approval for the target app in the interactive Codex CLI.** Desktop-app approvals are session-scoped; headless runs auto-decline the prompt → `Computer Use was not approved to use FileMaker Pro` → BLOCKED |
| **Claude computer-use MCP** (`mcp__computer-use__app_*`, background mode) | yes — `app_screenshot` returns image + AX summary with element coords | yes, from the AX summary and image | yes, in-memory (not saved to disk) | menus via `app_menu` (`View > Go to Layout > BASE` worked); clicks work; **typing into a non-empty field fails** (FileMaker exposes no AX write); typing into an empty field landed once | seeds ground truth by hand for local files | needs `request_access` once per session (an approval card the human clicks) |
| **AppleScript → FileMaker Pro** *(FileMaker)* | no | `cell` reads possible in principle | no | `create new record`, `set cell` | would be ideal for seeding | **refused** — `Your access privileges do not allow this action (-10004)` unless the account has the `fmextscriptaccess` extended privilege; schema enumeration also timed out with a second file open |
| **Data API / OData / ExecuteSQL** *(FileMaker)* (`fm-dataapi`, `fm-odata`, proofkit `execute_filemaker_sql`) | no | **yes — persisted values by primary key; the preferred channel for every data assertion** | no | script execution via Data API `script` param | seed fixtures and run reset scripts | yes, hosted files only |
| **OttoFMS** (`fm-otto`) *(FileMaker)* | no | no | no | no | **deploy a fresh copy of the fixture file = clean reset** | yes |
| **FileMaker-side screenshot plugin** (Joe's, 2026-09) *(FileMaker)* | — | — | from inside the file, via script | — | — | not yet wired here — location and API to be recorded |
| **Verifier** (fresh Codex or Claude context, Ringer task) | reads the runner's PNGs | compares receipt values to `truth.json` | no | no | no | yes |

## Which channel for which assertion

| Assertion type | Channel | Why |
|---|---|---|
| value persisted | the app's non-UI channel: Data API / ExecuteSQL (FileMaker), SQLite / defaults / API (native) | exact, cheap, independent of the runner |
| field value *as rendered* (`?`, formatting, conditional format) | runner AX read + screenshot | only the client knows how it painted |
| dialog text | runner screenshot at the `dialog-shown` checkpoint + verbatim AX read | dismissed dialogs leave no data trace |
| layout / mode / window state | runner AX (layout pop-up, view toggles) | toolbar exposes it as text |
| record count in found set | runner toolbar read, cross-checked by Data API query | both should agree |
| action really ran | a log table, run-tagged field, or log file the action writes | UI can be faked by a stale record |
| a native app's own UI test exists | XCUITest / Playwright first | headless, deterministic; this pattern covers the rest |

## Costs seen

| Run | Tokens | Wall |
|---|---|---|
| Codex design review (research) | 56k | 172 s |
| Codex probe, blocked at approval ×2 | 33k | 76 s |
| Codex probe, screenshot + 10 AX reads, PASS | 21k | 74 s |
