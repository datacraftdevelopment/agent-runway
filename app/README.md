# Runway app

SwiftUI, macOS 14+. Builds with Command Line Tools alone (no Xcode needed).

```bash
swift build && swift test        # RunwayCore models and the status decoding tests
bash make-app.sh --open          # build/Runway.app, a menu bar app with no Dock icon
```

- `RunwayCore`: the models for `runway status --json`, no UI. The app holds no rules; it draws the status and its
  buttons run `runway` commands.
- `Runway`: the main window (Board and Activity), the side panel (keep on top), the menu bar extra, the first-run
  screen.

`make-app.sh` copies the `runway` command (`../bin`, `../runway`) into the app. The app runs it through the login
shell, reads `runway status --json` every 3 seconds, and starts `runway loop` as its child: quitting the app stops
the loop (runs already started finish in tmux). Before the first run, on this Mac:

```bash
../bin/runway doctor                              # tools and sign-ins; fills the first-run table
../bin/runway repo add ~/path/to/clone            # a GitHub clone with a runway.json (check_cmd)
../bin/runway file < batch.json                   # or: runway file --repo <name> ticket.md …
```

With no `runway` command found, or with `RUNWAY_STATUS_FILE` set, the app shows that file (or the bundled sample),
labelled "Sample data". Launch switches for trying screens and taking screenshots:

| Variable | Effect |
| --- | --- |
| `RUNWAY_OPEN=panel,menu,setup` | Also open the side panel, the menu's content in a window, the first-run screen |
| `RUNWAY_TAB=activity` | Open the main window on Activity |
| `RUNWAY_SELECT=T-14` | Select that ticket in the inspector |
| `RUNWAY_NO_LOOP=1` | Don't start the loop |
| `RUNWAY_RENDER=<folder>` | Render each screen offscreen to PNGs and quit |

```bash
RUNWAY_OPEN=panel build/Runway.app/Contents/MacOS/Runway
```

Screenshots of each screen: `docs/shipped/screens/`.
