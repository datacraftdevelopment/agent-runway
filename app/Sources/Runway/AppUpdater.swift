import Foundation
import Sparkle
import RunwayCore

/// Owns Sparkle. With no `SUPublicEDKey` in Info.plist the controller is never created, so a build without the
/// update key can't check for or accept an update. Sparkle checks once a day on its own (`SUEnableAutomaticChecks`
/// and `SUScheduledCheckInterval`, written by make-app.sh) and verifies each download's EdDSA signature and the
/// new app's Developer ID before it installs it.
@MainActor
final class AppUpdater {
    static let shared = AppUpdater()

    let state: UpdaterState
    private let controller: SPUStandardUpdaterController?

    private init(bundle: Bundle = .main) {
        let env = ProcessInfo.processInfo.environment
        // Sample data and offscreen rendering are for trying screens; they never update the app.
        let enabled = env["RUNWAY_STATUS_FILE"] == nil && env["RUNWAY_RENDER"] == nil
        state = UpdaterState.decide(publicKey: bundle.object(forInfoDictionaryKey: "SUPublicEDKey") as? String,
                                    enabled: enabled)
        controller = state == .on
            ? SPUStandardUpdaterController(startingUpdater: true, updaterDelegate: nil, userDriverDelegate: nil)
            : nil
    }

    var version: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "dev"
    }

    func checkForUpdates() { controller?.checkForUpdates(nil) }
}
