import Foundation

/// Where the running Runway.app sits, and whether to offer moving it to Applications. Sparkle can only replace an
/// app it can write to and that macOS hasn't translocated, so a copy run from Downloads (or straight off the disk
/// image) never updates.
public enum AppLocation: Equatable {
    /// In /Applications or ~/Applications: nothing to do.
    case installed
    /// Somewhere a person put it by hand (Downloads, the Desktop, a mounted DMG, a translocated copy): offer the move.
    case elsewhere
    /// A developer build (make-app.sh's build/ folder, Xcode's DerivedData, a bare binary): never ask.
    case development

    public static func classify(bundlePath: String, home: String) -> AppLocation {
        let path = (bundlePath as NSString).standardizingPath
        guard path.hasSuffix(".app") else { return .development }
        let parent = (path as NSString).deletingLastPathComponent
        if parent == "/Applications" || parent == (home as NSString).appendingPathComponent("Applications") {
            return .installed
        }
        let parts = Set(path.split(separator: "/").map(String.init))
        if parent.hasSuffix("/build") || parts.contains("DerivedData") || parts.contains(".build") {
            return .development
        }
        return .elsewhere
    }
}
