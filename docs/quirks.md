# Quirks

Non-obvious gotchas worth remembering. Check before re-inventing fixes.

> Format: short heading, one or two sentences. Date-stamped. Add new entries at the top. The point is fast scanning, not exhaustive documentation.

## An allow-listed command must be run by name, without a heredoc (2026-10-24)

With `--allowedTools 'Bash(runway:*)'`, a session that found runway with `command -v` and then ran it by its full
path was refused, and so was `runway file <<'EOF' … EOF`. The skills say to run plain `runway`, and the batch goes
in a file: `runway file --batch <file.json>`.

## Codex loads Claude-format marketplaces, and repo skills under .agents/skills (2026-10-24)

`codex plugin marketplace add <folder with .claude-plugin/marketplace.json>` then `codex plugin add name@market`
works with the same plugin Claude Code installs (`claude plugin marketplace add`, `claude plugin install`); a
`.codex-plugin/plugin.json` beside `.claude-plugin/plugin.json` adds Codex's own fields. Symlinked skills in a repo's
`.agents/skills/` show up named after the plugin they resolve into. `CLAUDE_CONFIG_DIR` and `CODEX_HOME` point both at
throwaway config folders for testing installs.

## Claude's allow-list refuses chained commands (2026-10-24)

With `--permission-mode dontAsk --allowedTools 'Bash(python3 -m unittest -q:*)' 'Bash(git diff:*)'`, a reviewer that
ran `git diff … && python3 -m unittest -q; echo EXIT=$?` was refused as one command and gave up instead of retrying
them separately. Each pattern alone works (`:*` and ` *` forms both match). The worker prompts now list the allowed
commands and say to run each on its own; the next review ran with no refusals.

## A fix pass can't reuse the ticket's branch while an old worktree holds it (2026-10-24)

`git worktree add -B rw/T-3 …` fails with "cannot force update the branch used by worktree" while the earlier
build's worktree still has it checked out, even with `--force`. The loop removes the ticket's finished runs'
worktrees before a fix pass.

## Screenshots need an unlocked screen (2026-10-24)

`screencapture -l <window>` and `-R` fail with "could not create image" while the Mac is locked
(`ioreg -n Root -d1 | grep IOConsoleLocked`). `RUNWAY_RENDER=<folder>` renders the app's screens offscreen instead,
but `ImageRenderer` leaves ScrollView contents and text fields blank.

## Codex 0.164 has no --full-auto (2026-10-24)

`codex exec -s workspace-write` is the sandbox flag; `--add-dir` makes another folder writable (the run folder for
the outcome file). `--json` prints events, the first carrying the session's `thread_id` for `codex resume`.

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
