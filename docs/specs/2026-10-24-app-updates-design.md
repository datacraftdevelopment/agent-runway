# Design: the Runway app is signed and updates itself

Status: design and build, 2026-10-24. Carries over Runway v1's update design (Sparkle, Developer ID, a release
command only the person runs), moved to this public repo so the releases need no separate repo.

## Decisions

- **Sparkle 2** (pinned exactly in `app/Package.swift`) is the updater. It checks once a day and on "Check for
  Updates…" in the menu bar menu. A build without `app/sparkle-public-key` has the updater off and says so in the
  menu; it never accepts an unsigned update.
- **Releases are GitHub Releases on this repo**, tagged `v<app/VERSION>`, each with `Runway.zip` and `appcast.xml`.
  The asset names never change, so `releases/latest/download/Runway.zip` is the website's download link and
  `releases/latest/download/appcast.xml` is the feed. No other kind of release is published here.
- **Version:** `app/VERSION` is the marketing version; `CFBundleVersion` is the commit count, so it only goes up.
- **One release command, two places to run it:** `make-app.sh --release` signs inside out with Developer ID and the
  hardened runtime, notarizes, staples, zips, signs the zip with Sparkle's EdDSA key, writes the appcast, tags and
  publishes. It runs on the person's Mac (keychain) or in the `release` workflow (secrets in a throwaway keychain).
  `--dry-run` needs no secrets and runs on every PR in the `app` workflow.
- **Releases are the person's.** Publishing reaches every installed copy and can't be taken back, so no agent cuts
  one without the person's go.
- **Secrets never enter the repo:** the certificate, the notary credentials and Sparkle's private key live in a
  keychain or in GitHub Actions secrets. Only Sparkle's public key is committed.

## Out of scope

A DMG, beta channels, delta updates, updating the plugins or skills from the app (the `runway` command already rides
inside the app).

## Acceptance

- [ ] A1: The `app` workflow passes on a PR: tests, a release dry run, and a dry-run app that holds Sparkle.framework.
- [ ] A2: The `release` workflow (or `make-app.sh --release`) publishes `v<VERSION>`; the downloaded `Runway.zip`
  opens on a Mac that never built it with no Gatekeeper warning (`spctl --assess` accepts it).
- [ ] A3: With `0.1.0` installed and `0.1.1` released, "Check for Updates…" offers 0.1.1, installs it and relaunches,
  and the menu then shows 0.1.1.
- [ ] A4: `releases/latest/download/Runway.zip` downloads the newest release (the website's link).
