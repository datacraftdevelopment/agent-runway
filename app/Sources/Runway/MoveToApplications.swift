import AppKit
import RunwayCore

/// On launch from anywhere but Applications (Downloads, the disk image, a translocated copy), offers to move Runway
/// into Applications and relaunch it from there. Updates only work from Applications: Sparkle can't replace a copy
/// macOS has translocated or one sitting on a read-only disk image.
@MainActor
enum MoveToApplications {
    private static let declinedKey = "moveToApplicationsDeclined"

    static func offerIfNeeded() {
        let env = ProcessInfo.processInfo.environment
        guard env["RUNWAY_STATUS_FILE"] == nil, env["RUNWAY_RENDER"] == nil, env["RUNWAY_NO_MOVE"] == nil else { return }
        let source = Bundle.main.bundleURL
        guard AppLocation.classify(bundlePath: source.path, home: NSHomeDirectory()) == .elsewhere,
              !UserDefaults.standard.bool(forKey: declinedKey) else { return }

        NSApp.activate(ignoringOtherApps: true)
        let alert = NSAlert()
        alert.messageText = "Move Runway to your Applications folder?"
        alert.informativeText = "Runway can only keep itself up to date from Applications. It will move itself there and reopen."
        alert.addButton(withTitle: "Move to Applications")
        alert.addButton(withTitle: "Not Now")
        alert.showsSuppressionButton = true
        alert.suppressionButton?.title = "Don't ask again"
        let answer = alert.runModal()
        if alert.suppressionButton?.state == .on { UserDefaults.standard.set(true, forKey: declinedKey) }
        guard answer == .alertFirstButtonReturn else { return }

        do {
            let destination = try install(source)
            relaunch(destination)
        } catch {
            let failed = NSAlert()
            failed.messageText = "Runway couldn't move itself"
            failed.informativeText = "\(error.localizedDescription)\n\nDrag Runway into Applications in Finder, then open it from there."
            failed.runModal()
        }
    }

    /// Copies the app into /Applications (or ~/Applications when that isn't writable), replacing an older copy by
    /// moving it to the Trash. Copying works from a translocated or read-only source; the original stays where it was.
    private static func install(_ source: URL) throws -> URL {
        let fm = FileManager.default
        let system = URL(fileURLWithPath: "/Applications", isDirectory: true)
        let folder = fm.isWritableFile(atPath: system.path)
            ? system
            : fm.homeDirectoryForCurrentUser.appendingPathComponent("Applications", isDirectory: true)
        try fm.createDirectory(at: folder, withIntermediateDirectories: true)
        let destination = folder.appendingPathComponent(source.lastPathComponent)
        if fm.fileExists(atPath: destination.path) {
            try fm.trashItem(at: destination, resultingItemURL: nil)
        }
        try fm.copyItem(at: source, to: destination)
        // The person already chose to open this download; don't make Gatekeeper ask again for the moved copy.
        let xattr = Process()
        xattr.executableURL = URL(fileURLWithPath: "/usr/bin/xattr")
        xattr.arguments = ["-dr", "com.apple.quarantine", destination.path]
        try? xattr.run()
        xattr.waitUntilExit()
        return destination
    }

    /// Opens the moved copy once this process has gone, then quits.
    private static func relaunch(_ app: URL) {
        let opener = Process()
        opener.executableURL = URL(fileURLWithPath: "/bin/sh")
        opener.arguments = ["-c", "while kill -0 \(ProcessInfo.processInfo.processIdentifier) 2>/dev/null; do sleep 0.2; done; /usr/bin/open \"$0\"", app.path]
        try? opener.run()
        NSApp.terminate(nil)
    }
}
