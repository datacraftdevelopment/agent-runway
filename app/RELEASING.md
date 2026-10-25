# Releasing the Runway app

A release is a Developer ID-signed, notarized `Runway.zip` plus an `appcast.xml`, published as the GitHub release
`v<VERSION>` on this repo. Every installed Runway checks the feed once a day (and on "Check for Updates…" in the
menu), and Sparkle installs the new version after checking two things: the zip's EdDSA signature against the public
key built into the app, and the new app's Developer ID. The `runway` command rides inside the app, so an update brings
the matching command with it.

| What | Where |
| --- | --- |
| Download (website link, always the newest) | `https://github.com/datacraftdevelopment/agent-runway/releases/latest/download/Runway.zip` |
| Update feed (built into the app) | `https://github.com/datacraftdevelopment/agent-runway/releases/latest/download/appcast.xml` |
| One version | `https://github.com/datacraftdevelopment/agent-runway/releases/tag/v<VERSION>` |

Only app releases are published on this repo, because "latest" must always be the newest app.

## Cutting a release

1. Bump `app/VERSION` on a branch (e.g. `0.1.0` to `0.2.0`) and write `app/release-notes/<VERSION>.md`: a few plain
   `- ` lines. The same file is the release page (and so Sparkle's update window) and the app's What's New screen. For
   a major release, start it with front matter `---` / `big: true` / `---` and add `### ` sections: What's New shows
   each as a step in a fuller recap (the front matter is stripped from the release page). Merge to `main`.
2. Publish, one of:
   - **GitHub Actions:** Actions > release > Run workflow, on `main`. Needs the secrets below.
   - **This Mac:** on a clean `main`, `RUNWAY_SIGN_IDENTITY="Developer ID Application: …" RUNWAY_NOTARY_PROFILE=runway-notary bash app/make-app.sh --release`.

Both run the same `make-app.sh --release`, which refuses on a dirty tree, off `main`, when `v<VERSION>` already exists,
or when the tests fail. `--release --dry-run` does everything except notarize and publish, needs no secrets, and runs
in CI on every PR.

`--release --no-publish` signs, notarizes and staples `build/release/Runway.zip` from any branch, with no tag and no
release: the build to download onto a clean Mac and try as a new user would. It needs the same identity and notary
settings as a real release.

A release can't be quietly taken back: copies that already updated keep it. Fix forward with a higher version.

## One-time setup (the Apple Developer account holder)

Nothing below ever goes into the repo. The only key that is committed is Sparkle's **public** key.

1. **Developer ID Application certificate.** Xcode > Settings > Accounts > your team > Manage Certificates > `+` >
   Developer ID Application. It lands in this Mac's login keychain. `security find-identity -v -p codesigning` shows
   its full name, which is `RUNWAY_SIGN_IDENTITY`.
2. **Notarization credentials.**
   - For this Mac: an app-specific password from account.apple.com, then
     `xcrun notarytool store-credentials runway-notary --apple-id <you> --team-id <TEAMID>`.
   - For GitHub Actions: an App Store Connect API key (App Store Connect > Users and Access > Integrations >
     Team Keys, role Developer). Download the `.p8` once; note its Key ID and the Issuer ID.
3. **Sparkle update key.** `cd app && swift build` (fetches Sparkle), then
   `.build/artifacts/sparkle/Sparkle/bin/generate_keys`. It keeps the private key in this Mac's login keychain and
   prints the public key; put that in `app/sparkle-public-key` and commit it. If it says a key already exists, that
   key is fine to use. Back the private key up (`generate_keys -x sparkle-private.key`, then store the file in your
   password manager and delete it): **losing it means installed copies can never update again.**
4. **GitHub Actions secrets** (only for releasing from Actions), in this repo's Settings > Secrets and variables >
   Actions:

   | Secret | Value |
   | --- | --- |
   | `RUNWAY_CERT_P12` | Keychain Access > the Developer ID Application certificate > Export as `.p12` with a password, then `base64 -i cert.p12 \| pbcopy` |
   | `RUNWAY_CERT_PASSWORD` | that password |
   | `RUNWAY_NOTARY_KEY_P8` | `base64 -i AuthKey_XXXX.p8 \| pbcopy` |
   | `RUNWAY_NOTARY_KEY_ID` | the API key's Key ID |
   | `RUNWAY_NOTARY_ISSUER` | the Issuer ID |
   | `SPARKLE_PRIVATE_KEY` | the contents of the file from `generate_keys -x` |

   Delete the exported `.p12`, `.p8` and key files afterwards. The workflow puts them in a throwaway keychain on the
   runner and removes it when the job ends. Secrets are never given to workflows run from forks.

## Local builds

`bash make-app.sh` stays ad-hoc signed, for this Mac only. With `sparkle-public-key` committed, a local build checks
the feed too, and Sparkle will offer to replace it with the newest release. Run local builds with
`RUNWAY_STATUS_FILE` set (sample data), or just decline, if you don't want that.
