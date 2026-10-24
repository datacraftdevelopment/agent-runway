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

## Other Macs: how they connect today, and the two seams it needs

Checked 2026-10-24 against the app branch (`runway-app/local-run`, PR #6).

**Today.** One Mac runs Runway: it holds `~/.runway/runway.db` and runs the loop as the app's child. Tickets run only
on that Mac (`free_slots` only counts `kind='this_mac'`; `ssh_mac` and `cloud` exist in the `runners` table but
nothing runs there yet). There is no SSH code yet.

**The free model, without a daemon.** A Mac you sit at (say a laptop) and a Mac that stays home (say a desktop) both
have the app, and one of them is the Runway Mac. Other Macs are reached over plain SSH, with Tailscale so it works away
from home. Nothing listens or runs in the background on them: tickets run there inside tmux, started over SSH.

**Seam A: one runner object per runner, not one for the loop.** The loop already goes through a single `LocalRunner`
(`runway/runner.py`: `worktree`, `start`, `alive`, `stop`, `check`, `commit`, `push`, `remove`, `config`), which is
the right shape. What has to change before SSH lands:
- the loop holds a runner per row of `runners`, chosen by `kind` (`this_mac` → `LocalRunner`, `ssh_mac` →
  `SSHRunner`, which runs the same git/tmux commands through `ssh <host>`), registered through the extension list
  above rather than an `if kind ==` chain;
- everything the loop does on a run goes through the runner, keyed by run id: `read`, `write` (the prompt),
  `exec` in the worktree (check, commit, push, PR), `start`, `alive`, `stop`. `run_dir` becomes private to
  `LocalRunner`, because on an SSH Mac the run files live on that Mac (`loop.py` reads and writes `run_dir / …`
  directly today);
- each runner knows where each repo is cloned on it (a per-runner, per-repo path), which is also what makes a repo's
  main computer real.

**Seam B: the app talks to its Runway Mac through a connection.** `RunwayCLI.swift` runs `runway <args>` in the local
login shell. Give it a connection setting: this Mac (as now), or another Mac over SSH (`ssh <host> runway <args>`,
same JSON back). Then the laptop's app can show and drive the board on the desktop without the database moving, and
switching which Mac is "home" is one setting. Only the home Mac's app runs the loop (as its child, so still no
daemon, but the home Mac must be awake with the app open); an app connected over SSH is a remote control and never
starts a second loop, so `RunwayCLI` refuses `loop` on an SSH connection. The app stays logic-free either way.

Both seams are small, keep the free model daemon-free, and leave room for other connection and runner types later.

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
