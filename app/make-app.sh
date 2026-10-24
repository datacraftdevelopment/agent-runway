#!/usr/bin/env bash
# Build the Runway app in release mode and wrap it in build/Runway.app (menu bar app, no Dock icon).
#   bash make-app.sh          # build only
#   bash make-app.sh --open   # build, then open it
# Works with Command Line Tools alone. For now the app reads the sample status file copied in below.
set -euo pipefail
OPEN=0
for arg in "$@"; do
  case "$arg" in
    --open) OPEN=1 ;;
    *) echo "make-app.sh: unknown option $arg" >&2; exit 2 ;;
  esac
done
cd "$(dirname "$0")"

APP="build/Runway.app"
VERSION="$(tr -d '[:space:]' < VERSION)"
COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"

swift build -c release
BIN="$(swift build -c release --show-bin-path)/Runway"

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources"
cp "$BIN" "$APP/Contents/MacOS/Runway"
cp Tests/RunwayCoreTests/Fixtures/sample-status.json "$APP/Contents/Resources/sample-status.json"

# The runway command rides inside the app (Python, stdlib only), so the app finds it without an install step.
mkdir -p "$APP/Contents/Resources/cli/bin" "$APP/Contents/Resources/cli/runway"
cp ../bin/runway "$APP/Contents/Resources/cli/bin/runway"
cp ../runway/*.py "$APP/Contents/Resources/cli/runway/"
chmod +x "$APP/Contents/Resources/cli/bin/runway"

cat > "$APP/Contents/Info.plist" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>CFBundleName</key><string>Runway</string>
  <key>CFBundleDisplayName</key><string>Runway</string>
  <key>CFBundleIdentifier</key><string>dev.datacraft.runway-agent</string>
  <key>CFBundleExecutable</key><string>Runway</string>
  <key>CFBundlePackageType</key><string>APPL</string>
  <key>CFBundleShortVersionString</key><string>$VERSION</string>
  <key>CFBundleVersion</key><string>$VERSION</string>
  <key>RunwayBuildCommit</key><string>$COMMIT</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
</dict>
</plist>
PLIST

# Ad-hoc sign so macOS will launch it locally. No Developer ID, no notarisation (not in this plan).
codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || echo "warning: ad-hoc codesign failed"

ABS="$(cd "$(dirname "$APP")" && pwd)/$(basename "$APP")"
echo "Built $ABS"
[ "$OPEN" = 1 ] && open "$ABS"
exit 0
