# Extension points: three small seams

Status: design, 2026-10-24. Leave room for other builds of Agent Runway (another team's runner, a separately
distributed edition) to add to the app instead of forking it. Nothing built. The seams land after the app PRs (#5, #6, #8) are on main, so
this doesn't collide with them.

## Rule

This repo never knows what an extension contains. It only offers places to plug in, uses them itself for at least one
built-in feature (so they stay tested and honest), and works the same with nothing plugged in. No licence checks, no
feature flags, no extension code in this repo.

## The seams

1. **The `runway` command loads extensions.** At start it imports every module listed in `~/.runway/extensions.json`
   (or found as an installed `runway_ext_*` package). An extension can register: a runner type (a new place tickets
   run), a gate rule (an extra condition before auto-merge, which can only make the gate stricter), a CLI subcommand,
   and extra fields under `extensions.<name>` in `runway status --json`. The built-in SSH runner registers itself the
   same way. Rules stay in Python, so the app still holds no logic.
2. **The app's UI is a library with one thin executable.** Split the Swift package into `RunwayUI` (every view, the
   model, the menu bar) and a few-line `Runway` executable that starts it. `RunwayUI` takes a list of
   `RunwayExtension` values that can add a sidebar section, an inspector panel for a ticket, a settings tab and a
   first-run step. Another edition is then its own package that depends on `RunwayUI`, registers its extensions and
   ships its own signed app, with its own update feed.
3. **Status passes through what it doesn't know.** `RunwayCore`'s status decoding keeps any `extensions` object as raw
   JSON, so an extension's panel can read its own data without the core models changing.

## Not now

Loading extensions from the app's own settings screen, or any marketplace for them. App Store distribution is out: the Mac App Store requires the App Sandbox, and anything a sandboxed app starts inherits
it, so the person's own `claude`, `codex`, `git`, `ssh` and `tmux` would be cut off from their repos, sign-ins and
SSH keys. So both editions ship as notarised Developer ID downloads.

## Acceptance

- [ ] A1: With no extensions installed, the app and `runway` behave exactly as before; the test suites pass unchanged.
- [ ] A2: A sample extension in `tests/` adds a runner type, a gate rule and a status field, and the app shows its
  field in a sample inspector panel, with no change to the core code beyond the seams.
- [ ] A3: A separate package outside the repo builds an app from `RunwayUI` plus one extension. Verify: `swift build`
  in a scratch folder.
