#!/usr/bin/env bash
# Build the Runway app in release mode and wrap it in build/Runway.app (menu bar app, no Dock icon).
#   bash make-app.sh                     # build, ad-hoc signed, for this Mac
#   bash make-app.sh --open              # build, then open it
#   bash make-app.sh --release           # sign with Developer ID, notarize, staple, zip, sign the zip for Sparkle,
#                                        # write appcast.xml, tag v<VERSION> and publish the GitHub release
#   bash make-app.sh --release --dry-run # all of that except notarize and publish; output in build/release/
#   bash make-app.sh --release --no-publish # signed, notarized and stapled into build/release/, from any branch,
#                                        # with no tag and no GitHub release: a build to try as a new user would
# Works with Command Line Tools alone. --release needs, from the environment (RELEASING.md has the one-time setup):
#   RUNWAY_SIGN_IDENTITY   the Developer ID Application identity, e.g. "Developer ID Application: Name (TEAMID)"
#   notarization, one of:  RUNWAY_NOTARY_PROFILE (a notarytool keychain profile)
#                          or RUNWAY_NOTARY_KEY + RUNWAY_NOTARY_KEY_ID + RUNWAY_NOTARY_ISSUER (App Store Connect API key)
#   SPARKLE_KEY_FILE       optional: the Sparkle private key as a file (CI). Without it sign_update reads the keychain.
# No secret is ever written into the repo, the app or the log.
set -euo pipefail
OPEN=0; RELEASE=0; DRY=0; NOPUB=0
for arg in "$@"; do
  case "$arg" in
    --open) OPEN=1 ;;
    --release) RELEASE=1 ;;
    --dry-run) DRY=1 ;;
    --no-publish) NOPUB=1 ;;
    *) echo "make-app.sh: unknown option $arg" >&2; exit 2 ;;
  esac
done
[ "$DRY" = 1 ] && [ "$RELEASE" = 0 ] && { echo "make-app.sh: --dry-run only goes with --release" >&2; exit 2; }
[ "$NOPUB" = 1 ] && [ "$RELEASE" = 0 ] && { echo "make-app.sh: --no-publish only goes with --release" >&2; exit 2; }
[ "$NOPUB" = 1 ] && [ "$DRY" = 1 ] && { echo "make-app.sh: pick one of --dry-run and --no-publish" >&2; exit 2; }
[ "$OPEN" = 1 ] && [ "$RELEASE" = 1 ] && { echo "make-app.sh: --open and --release don't mix" >&2; exit 2; }
cd "$(dirname "$0")"

APP="build/Runway.app"
REPO="$(git rev-parse --show-toplevel)"
VERSION="$(tr -d '[:space:]' < VERSION)"
TAG="v$VERSION"
REL_DIR="build/release"
# Releases, their downloads and the update feed live on this (public) repo. The website links
# https://github.com/$GH_REPO/releases/latest/download/Runway.dmg, so the asset names never change. Runway.zip
# is what Sparkle downloads for updates.
GH_REPO="${RUNWAY_RELEASE_REPO:-datacraftdevelopment/agent-runway}"
FEED_URL="https://github.com/$GH_REPO/releases/latest/download/appcast.xml"

die() { echo "make-app.sh: $*" >&2; exit 1; }
# A real release stops on a refusal. A dry run reports it and carries on, so an agent in a worktree can test the rest.
refuse() {
  if [ "$DRY" = 1 ]; then echo "make-app.sh: would refuse: $*" >&2; else die "refusing to release: $*"; fi
}
# Checks that only guard publishing: --no-publish publishes nothing, so they only warn.
refuse_publish() {
  if [ "$NOPUB" = 1 ]; then echo "make-app.sh: note (not publishing): $*" >&2; else refuse "$@"; fi
}

if [ "$RELEASE" = 1 ]; then
  [ -z "$(git -C "$REPO" status --porcelain)" ] || refuse_publish "working tree is dirty (commit first)"
  BRANCH="$(git -C "$REPO" rev-parse --abbrev-ref HEAD)"
  # CI checks out the tag's commit detached; RUNWAY_RELEASE_REF=main says it is main's head.
  [ "$BRANCH" = main ] || [ "${RUNWAY_RELEASE_REF:-}" = main ] || refuse_publish "not on main (on $BRANCH)"
  if [ -z "${RUNWAY_SIGN_IDENTITY:-}" ]; then
    # A dry run without a certificate signs ad hoc (still with the hardened runtime), so the packaging is tested.
    [ "$DRY" = 1 ] || die "RUNWAY_SIGN_IDENTITY is not set (the Developer ID Application identity)"
    RUNWAY_SIGN_IDENTITY="-"; echo "make-app.sh: dry run with no RUNWAY_SIGN_IDENTITY: signing ad hoc" >&2
  fi
  if [ "$DRY" = 0 ] && [ -z "${RUNWAY_NOTARY_PROFILE:-}" ] && [ -z "${RUNWAY_NOTARY_KEY:-}" ]; then
    die "set RUNWAY_NOTARY_PROFILE, or RUNWAY_NOTARY_KEY with RUNWAY_NOTARY_KEY_ID and RUNWAY_NOTARY_ISSUER"
  fi
  [ -s sparkle-public-key ] || refuse "app/sparkle-public-key is missing; run Sparkle's generate_keys and commit the public key"
  # A missing or signed-out gh would make "no release" look like the answer, so check it first.
  if [ "$NOPUB" = 0 ]; then
    { command -v gh >/dev/null 2>&1 && gh auth status >/dev/null 2>&1; } || refuse "gh is missing or not signed in (gh auth login)"
    if gh release view "$TAG" -R "$GH_REPO" >/dev/null 2>&1; then refuse "$TAG already exists as a GitHub release"; fi
    # A tag that already points elsewhere would let the binary and the tagged source disagree. CI runs on the tag
    # itself, so a tag on HEAD is fine.
    if TAGGED="$(git -C "$REPO" rev-parse -q --verify "refs/tags/$TAG^{commit}")"; then
      [ "$TAGGED" = "$(git -C "$REPO" rev-parse HEAD)" ] || refuse "$TAG already exists on another commit"
    fi
  fi
  echo "== check"
  CHECK_CMD="${RUNWAY_RELEASE_CHECK_CMD:-cd $REPO && python3 -m unittest discover -s tests -t . && cd app && swift test}"
  bash -c "$CHECK_CMD" || refuse "check failed ($CHECK_CMD)"
fi

swift build -c release
BIN_DIR="$(swift build -c release --show-bin-path)"

# CFBundleVersion only ever goes up: the commit count of this checkout's history. Sparkle compares it.
COMMIT="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"
BUILD="$(git -C "$REPO" rev-list --count HEAD 2>/dev/null || echo 1)"
# The public key is committed and isn't secret. No key file means the updater is off, and the menu says so.
PUBKEY=""; [ -f sparkle-public-key ] && PUBKEY="$(tr -d '[:space:]' < sparkle-public-key)"
SPARKLE_KEYS=""
if [ -n "$PUBKEY" ]; then
  SPARKLE_KEYS="  <key>SUFeedURL</key><string>$FEED_URL</string>
  <key>SUPublicEDKey</key><string>$PUBKEY</string>
  <key>SUEnableAutomaticChecks</key><true/>
  <key>SUScheduledCheckInterval</key><integer>86400</integer>"
else
  echo "note: no sparkle-public-key, so the updater is off in this build"
fi

rm -rf "$APP"
mkdir -p "$APP/Contents/MacOS" "$APP/Contents/Resources" "$APP/Contents/Frameworks"
cp "$BIN_DIR/Runway" "$APP/Contents/MacOS/Runway"
cp Tests/RunwayCoreTests/Fixtures/sample-status.json "$APP/Contents/Resources/sample-status.json"
# The licence (with its Required Notice line) travels with every copy of the app.
cp "$REPO/LICENSE" "$APP/Contents/Resources/LICENSE"
# Release notes, one file per version: What's New reads them, and the GitHub release (Sparkle's notes link) shows the
# same file.
[ -d release-notes ] && cp -R release-notes "$APP/Contents/Resources/release-notes"

# The app icon, made from icon/AppIcon.png (1024 px) with the system's sips and iconutil.
ICON_KEY=""
if [ -f icon/AppIcon.png ]; then
  ICONSET="build/AppIcon.iconset"; rm -rf "$ICONSET"; mkdir -p "$ICONSET"
  for size in 16 32 128 256 512; do
    sips -z "$size" "$size" icon/AppIcon.png --out "$ICONSET/icon_${size}x${size}.png" >/dev/null
    sips -z "$((size * 2))" "$((size * 2))" icon/AppIcon.png --out "$ICONSET/icon_${size}x${size}@2x.png" >/dev/null
  done
  iconutil -c icns -o "$APP/Contents/Resources/AppIcon.icns" "$ICONSET"
  rm -rf "$ICONSET"
  ICON_KEY="  <key>CFBundleIconFile</key><string>AppIcon</string>"
fi

# Sparkle's framework rides in Contents/Frameworks; the binary finds it through an rpath.
cp -R "$BIN_DIR/Sparkle.framework" "$APP/Contents/Frameworks/"
install_name_tool -add_rpath @executable_path/../Frameworks "$APP/Contents/MacOS/Runway" 2>/dev/null || true

# The runway command rides inside the app (Python, stdlib only), so the app finds it without an install step,
# and an app update brings the matching command with it.
mkdir -p "$APP/Contents/Resources/cli/bin" "$APP/Contents/Resources/cli/runway"
cp "$REPO/bin/runway" "$APP/Contents/Resources/cli/bin/runway"
cp "$REPO"/runway/*.py "$APP/Contents/Resources/cli/runway/"
chmod +x "$APP/Contents/Resources/cli/bin/runway"
# The skills (one plugin for Claude Code and Codex) ride next to the command; first run installs them from here.
cp -R "$REPO/plugin" "$APP/Contents/Resources/cli/plugin"

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
  <key>CFBundleVersion</key><string>$BUILD</string>
  <key>RunwayBuildCommit</key><string>$COMMIT</string>
  <key>LSMinimumSystemVersion</key><string>14.0</string>
  <key>LSUIElement</key><true/>
  <key>NSHighResolutionCapable</key><true/>
$ICON_KEY
  <key>NSHumanReadableCopyright</key><string>Copyright 2026 DataCraft Development. Agent Runway, https://agentrunway.app</string>
$SPARKLE_KEYS
</dict>
</plist>
PLIST

if [ "$RELEASE" = 1 ]; then
  # Developer ID plus the hardened runtime, signed inside out as Sparkle's docs ask (no --deep). A dry run skips the
  # secure timestamp, which needs Apple's server.
  TS="--timestamp"; [ "$DRY" = 1 ] && TS="--timestamp=none"
  sign() { codesign --force --options runtime "$TS" --sign "$RUNWAY_SIGN_IDENTITY" "$@" \
    || die "codesign failed on $* (is the identity in this Mac's keychain? RUNWAY_SIGN_IDENTITY=$RUNWAY_SIGN_IDENTITY)"; }
  SP="$APP/Contents/Frameworks/Sparkle.framework/Versions/B"
  for xpc in "$SP"/XPCServices/*.xpc; do [ -e "$xpc" ] && sign --preserve-metadata=entitlements "$xpc"; done
  sign "$SP/Autoupdate"
  sign "$SP/Updater.app"
  sign "$APP/Contents/Frameworks/Sparkle.framework"
  sign "$APP"
  codesign --verify --deep --strict "$APP" || die "signature verification failed"
else
  # Ad-hoc sign so macOS will launch it on this Mac. Not for giving to anyone else.
  codesign --force --deep --sign - "$APP" >/dev/null 2>&1 || echo "warning: ad-hoc codesign failed"
fi

if [ "$RELEASE" = 1 ]; then
  rm -rf "$REL_DIR"; mkdir -p "$REL_DIR"
  ZIP="$REL_DIR/Runway.zip"
  if [ "$DRY" = 1 ]; then
    echo "== dry run: skipping notarize and staple"
  else
    echo "== notarize the app (a few minutes)"
    ditto -c -k --keepParent "$APP" "$REL_DIR/notarize.zip"
    if [ -n "${RUNWAY_NOTARY_PROFILE:-}" ]; then
      NOTARY=(--keychain-profile "$RUNWAY_NOTARY_PROFILE")
    else
      NOTARY=(--key "$RUNWAY_NOTARY_KEY" --key-id "${RUNWAY_NOTARY_KEY_ID:?}" --issuer "${RUNWAY_NOTARY_ISSUER:?}")
    fi
    xcrun notarytool submit "$REL_DIR/notarize.zip" "${NOTARY[@]}" --wait || die "notarization failed"
    rm -f "$REL_DIR/notarize.zip"
    xcrun stapler staple "$APP" || die "stapling failed"
    spctl --assess --type execute "$APP" || die "Gatekeeper rejects the notarized app"
  fi
  ditto -c -k --keepParent "$APP" "$ZIP"

  # The disk image people download: Runway.app beside an Applications shortcut, to drag one onto the other.
  # Sparkle keeps updating from the zip; the DMG is for first installs.
  DMG="$REL_DIR/Runway.dmg"
  STAGE="$REL_DIR/dmg"; rm -rf "$STAGE"; mkdir -p "$STAGE"
  ditto "$APP" "$STAGE/Runway.app"
  ln -s /Applications "$STAGE/Applications"
  hdiutil create -volname "Agent Runway" -srcfolder "$STAGE" -fs HFS+ -format UDZO -ov "$DMG" >/dev/null \
    || die "hdiutil create failed"
  rm -rf "$STAGE"
  codesign --force "$TS" --sign "$RUNWAY_SIGN_IDENTITY" "$DMG" || die "codesign failed on $DMG"
  if [ "$DRY" = 0 ]; then
    echo "== notarize the disk image (a few minutes)"
    xcrun notarytool submit "$DMG" "${NOTARY[@]}" --wait || die "notarization of the disk image failed"
    xcrun stapler staple "$DMG" || die "stapling the disk image failed"
    spctl --assess --type open --context context:primary-signature "$DMG" || die "Gatekeeper rejects the disk image"
  fi

  SIGN_UPDATE="${SPARKLE_SIGN_UPDATE:-$(find .build/artifacts -name sign_update -type f -perm -u+x 2>/dev/null | head -n 1)}"
  { [ -n "$SIGN_UPDATE" ] && [ -x "$SIGN_UPDATE" ]; } || die "Sparkle's sign_update not found (set SPARKLE_SIGN_UPDATE, or run swift build so the package's artifacts exist)"
  KEY_ARGS=(); [ -n "${SPARKLE_KEY_FILE:-}" ] && KEY_ARGS=(--ed-key-file "$SPARKLE_KEY_FILE")
  # Prints: sparkle:edSignature="..." length="..."
  if ! SIG="$("$SIGN_UPDATE" ${KEY_ARGS[@]+"${KEY_ARGS[@]}"} "$ZIP")"; then
    refuse "sign_update failed (is the Sparkle private key in this Mac's keychain, or SPARKLE_KEY_FILE set?)"
    SIG='sparkle:edSignature="DRY-RUN-UNSIGNED" length="0"'
  fi
  case "$SIG" in *sparkle:edSignature=*) ;; *) die "sign_update gave no signature" ;; esac
  SIG="$(printf '%s' "$SIG" | tr -d '\n')"

  # The feed holds only the newest version: Sparkle needs nothing more.
  # Sparkle's update window shows the version's own notes, written into the feed (the same file as What's New and
  # the release page), not the whole GitHub page. With no notes file it falls back to linking the release page.
  if [ -f "release-notes/$VERSION.md" ]; then
    NOTES_ITEM="<description><![CDATA[$(python3 notes-html.py "release-notes/$VERSION.md" "$VERSION")]]></description>"
  else
    NOTES_ITEM="<sparkle:releaseNotesLink>https://github.com/$GH_REPO/releases/tag/$TAG</sparkle:releaseNotesLink>"
  fi
  cat > "$REL_DIR/appcast.xml" <<APPCAST
<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:sparkle="http://www.andymatuschak.org/xml-namespaces/sparkle">
  <channel>
    <title>Runway</title>
    <item>
      <title>Runway $VERSION</title>
      <link>https://github.com/$GH_REPO/releases/tag/$TAG</link>
      $NOTES_ITEM
      <pubDate>$(LC_ALL=C date -u "+%a, %d %b %Y %H:%M:%S +0000")</pubDate>
      <sparkle:version>$BUILD</sparkle:version>
      <sparkle:shortVersionString>$VERSION</sparkle:shortVersionString>
      <sparkle:minimumSystemVersion>14.0</sparkle:minimumSystemVersion>
      <enclosure url="https://github.com/$GH_REPO/releases/download/$TAG/Runway.zip" type="application/octet-stream" $SIG/>
    </item>
  </channel>
</rss>
APPCAST
  if [ "$DRY" = 1 ]; then
    echo "Dry run done: $(pwd)/$DMG, $(pwd)/$ZIP and $(pwd)/$REL_DIR/appcast.xml (not notarized, not published)"
    exit 0
  fi
  if [ "$NOPUB" = 1 ]; then
    echo "Built $(pwd)/$DMG and $(pwd)/$ZIP: signed, notarized and stapled (not tagged, not published)"
    exit 0
  fi
  echo "== publish $TAG"
  SOURCE="$(git -C "$REPO" rev-parse HEAD)"
  if ! git -C "$REPO" rev-parse -q --verify "refs/tags/$TAG" >/dev/null; then
    git -C "$REPO" tag "$TAG" "$SOURCE" && git -C "$REPO" push origin "refs/tags/$TAG" || die "could not tag $SOURCE as $TAG"
  fi
  NOTES="Runway $VERSION (build $BUILD, source $SOURCE)."
  # The same file What's New shows, without its front matter (big: true).
  [ -f "release-notes/$VERSION.md" ] && NOTES="$(awk 'NR==1 && /^---$/ {fm=1; next} fm && /^---$/ {fm=0; next} !fm' "release-notes/$VERSION.md")"
  gh release create "$TAG" "$DMG" "$ZIP" "$REL_DIR/appcast.xml" -R "$GH_REPO" --verify-tag \
    --title "Runway $VERSION" --notes "$NOTES" || die "gh release create failed"
  echo "Published $TAG: https://github.com/$GH_REPO/releases/tag/$TAG"
  exit 0
fi

ABS="$(cd "$(dirname "$APP")" && pwd)/$(basename "$APP")"
echo "Built $ABS"
[ "$OPEN" = 1 ] && open "$ABS"
exit 0
