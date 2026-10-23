# Target profile — FileMaker Pro

**Approve:** `FileMaker Pro` (bundle `com.filemaker.client.pro12`) with "always"
scope in the interactive Codex CLI, once per machine.

**Preconditions to state:** window title (the file name), layout name, mode
(Browse/Find/Preview), view (Form/List/Table), current record by primary key,
account and privilege set, and the initial value of every field the action
should change.

**Non-UI channel:** Data API / OData / ExecuteSQL for hosted files
(`fm-dc` skills `fm-dataapi`, `fm-odata`, proofkit `execute_filemaker_sql`).
Local unhosted files have none — seed and read ground truth with the Claude
computer-use MCP instead.

**Reset:** redeploy the fixture file with OttoFMS (`fm-otto`), or run the
file's reset script through the Data API `script` parameter.

**What the AX tree exposes (observed 2026-09-12):** field values as text, the
layout pop-up title, view toggles, toolbar "Total (Unsorted) N". The AX value
is the *stored* value: a number field rendered as `?` (too narrow) reports its
full stored value (`6.1412E+57`), text in a number field reports the text
(`PROBE-7Q4M-2026`). Assertions about rendering must say `type: rendered` and
the runner must read them from pixels.

**Gotchas:**
- AppleScript `set cell` / `create new record` is refused (`-10004`) unless the
  account has the `fmextscriptaccess` extended privilege; schema enumeration
  timed out with a second file open.
- Claude's computer-use MCP typed into an empty field once, never into a
  non-empty one; `app_menu` works (`View > Go to Layout > <name>`).
- A modal dialog swallows keystrokes meant for the layout; the instruction
  names the one dialog the runner may dismiss.
- Worked example: `references/example-probe/`.
