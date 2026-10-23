# Quirks

Non-obvious gotchas worth remembering. Check before re-inventing fixes.

> Format: short heading, one or two sentences. Date-stamped. Add new entries at the top. The point is fast scanning, not exhaustive documentation.

## S3: Codex Cloud needs an environment first (2026-10-23)

`codex cloud exec --env <ENV_ID> [--branch <b>] "prompt"` submits a task without the TUI; `codex cloud list --json`,
`codex cloud status <TASK_ID>` and `codex cloud diff <TASK_ID>` read it back (codex-cli 0.164). On the main Mac it
stopped at `Error: no cloud environments are available for this workspace`: an environment for the repo has to be
created once in the Codex web UI, and there is no CLI command to list or create one (`codex cloud` with no command
opens the TUI browser). Setup's cloud step must send the person there. Not yet tried end to end.

## S3: `claude --cloud` creates a session only interactively (2026-10-23)

`claude --cloud "<description>"` creates a Claude Code cloud session (v2.1.308), but `-p` refuses it: "Starting a new
cloud session with --cloud is interactive only". Messaging an existing one is headless: `claude -p "msg" --cloud
<session-id>`. Run in a detached tmux, `claude --cloud` stopped at the first-run onboarding (theme, then security
notes), as if the tmux server saw no existing config; not clicked through. So the loop can't create cloud sessions
headless yet. Options to try: drive the interactive create in tmux after onboarding is done once in tmux, or use the
cloud API/`/schedule`-style routines. Finished signal: the PR (no CLI status command found).

## S2: Codex works over SSH, Claude Code reports signed out (2026-10-23)

From the main Mac, `ssh <mac> 'zsh -lc "codex exec --skip-git-repo-check \"say ok\""'` answered `ok` (Codex keeps
its sign-in in a file under `~/.codex/`). The same for `claude -p "say ok"` printed `Not logged in · Please run
/login`, and `claude auth status` said `"loggedIn": false, "authMethod": "none"`. Likely cause: Claude Code keeps its
sign-in in the login keychain, which a non-interactive SSH session can't read; not confirmed (it may simply be signed
out on that Mac). Candidate fixes, none applied: `claude setup-token` on that Mac and export
`CLAUDE_CODE_OAUTH_TOKEN` for SSH sessions, or `security unlock-keychain` in the SSH session. Setup must check
`claude auth status` over SSH, not locally. Also: a login shell (`zsh -lc`) is needed for PATH (`~/.local/bin`,
npm globals).

## S1: SwiftUI builds with Command Line Tools alone (2026-10-23)

`swift build` of a `MenuBarExtra` + `WindowGroup` app (macOS 14 target) builds and opens a window with only Command
Line Tools selected (Swift 6.4; two harmless `ld` search-path warnings). Xcode 27.1 is installed but `xcode-select`
points at CLT, so `xcodebuild` fails; `DEVELOPER_DIR=/Applications/Xcode.app/Contents/Developer swift build` works
without changing the system setting. `swift test` runs XCTest under CLT too (checked in task 1.1).
