import Foundation

/// Whether the app may check for updates. Sparkle only runs when the build carries a public key, so a build without
/// one (a local `make-app.sh` build before the key exists) never accepts an unsigned update and never crashes.
public enum UpdaterState: Equatable {
    case on
    case off

    /// `publicKey` is `SUPublicEDKey` from Info.plist; `make-app.sh` leaves it out when there's no key file.
    /// `enabled: false` (sample data, offscreen rendering) keeps Sparkle off whatever Info.plist says.
    public static func decide(publicKey: String?, enabled: Bool = true) -> UpdaterState {
        guard enabled, let key = publicKey?.trimmingCharacters(in: .whitespacesAndNewlines), !key.isEmpty else {
            return .off
        }
        return .on
    }

    /// The menu line shown instead of "Check for Updates…" when the updater is off.
    public var menuNote: String? {
        self == .off ? "Updates off in this build" : nil
    }
}
