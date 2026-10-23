# Target profile — native macOS app (Swift / SwiftUI / AppKit / Catalyst)

**Approve:** the app by display name, "always" scope, in the interactive Codex
CLI. A debug build has the same bundle id as release unless you changed it —
approve once. If the bundle id changes per build the approval will not carry.

**First choice check:** if the project has an XCUITest target, that is the
headless path — write the test there and keep this pattern for what XCUITest
can't reach (cross-app flows, system dialogs, visual regressions, an app with
no test target yet).

**Make the AX tree tell the truth.** Runner reads are exact when controls carry
identifiers: set `.accessibilityIdentifier("invoice-status")` on SwiftUI views
and `accessibilityIdentifier` on AppKit controls for every field an assertion
names, and reference those ids in the instruction (`target: ax id
"invoice-status"`). Without ids the runner falls back to label text and pixels
and the receipt's `source` will say so.

**Preconditions to state:** window title, the screen or view visible (by AX
identifier or title), the fixture or record identity, signed-in account, the
app's build id (`CFBundleVersion` — read it from the running app's Info.plist
and put it in `truth.json` so a stale build cannot pass).

**Non-UI channel:** whatever the app persists — its SQLite/Core Data store
(read with `sqlite3` on a copy), `UserDefaults` (`defaults read <bundle id>`),
files in its container, or its API. Assert persisted values there, not from
pixels.

**Launch and reset:** build with `xcodebuild`, then `open -n <path>.app` or
launch the binary with a `--fixture <name>` flag you add for tests. Reset =
quit, wipe the container or defaults for the test account, relaunch. Put the
exact launch command in the instruction's preconditions so the runner can
verify the right build is up, not launch it — launching stays with the
orchestrator.

**Gotchas:**
- Sheets and alerts are separate AX windows; the instruction names the
  expected alert text and the checkpoint (`alert-shown`).
- SwiftUI `Text` without an identifier may merge with neighbours in the AX
  tree; assert on identified controls.
- Menu bar commands are reachable to the runner; keyboard shortcuts into a
  background window are not reliable — name the menu path.
