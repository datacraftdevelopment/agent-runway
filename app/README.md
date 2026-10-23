# Runway app

SwiftUI, macOS 14+. Builds with Command Line Tools alone (no Xcode needed).

```bash
swift build && swift test        # RunwayCore models and the status decoding tests
bash make-app.sh --open          # build/Runway.app, a menu bar app with no Dock icon
```

- `RunwayCore`: the models for `runway status --json`, no UI. The app holds no rules; it draws the status and its
  buttons will run `runway` commands (Phase 2). For now every button only logs what it would run.
- `Runway`: the main window (Board and Activity), the side panel (keep on top), the menu bar extra, the first-run
  screen.

For now the app reads `Tests/RunwayCoreTests/Fixtures/sample-status.json` (copied into the app by `make-app.sh`), or
the file named by `RUNWAY_STATUS_FILE`. Launch switches for trying screens and taking screenshots:

| Variable | Effect |
| --- | --- |
| `RUNWAY_OPEN=panel,menu,setup` | Also open the side panel, the menu's content in a window, the first-run screen |
| `RUNWAY_TAB=activity` | Open the main window on Activity |
| `RUNWAY_SELECT=T-14` | Select that ticket in the inspector |

```bash
RUNWAY_OPEN=panel build/Runway.app/Contents/MacOS/Runway
```

Screenshots of each screen: `docs/shipped/screens/`.
