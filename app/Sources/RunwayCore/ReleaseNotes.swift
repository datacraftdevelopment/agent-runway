import Foundation

/// A version like 0.1.1, compared number by number (so 0.10.0 is newer than 0.9.0). Anything after a `-` is ignored.
public struct AppVersion: Comparable, CustomStringConvertible, Sendable {
    public let parts: [Int]

    public init?(_ text: String) {
        let core = text.trimmingCharacters(in: .whitespaces).split(separator: "-").first.map(String.init) ?? ""
        let parts = core.split(separator: ".", omittingEmptySubsequences: false).map { Int($0) }
        guard !parts.isEmpty, parts.allSatisfy({ $0 != nil }) else { return nil }
        self.parts = parts.compactMap { $0 }
    }

    public var description: String { parts.map(String.init).joined(separator: ".") }

    public static func < (a: AppVersion, b: AppVersion) -> Bool {
        for i in 0..<max(a.parts.count, b.parts.count) {
            let x = i < a.parts.count ? a.parts[i] : 0, y = i < b.parts.count ? b.parts[i] : 0
            if x != y { return x < y }
        }
        return false
    }

    public static func == (a: AppVersion, b: AppVersion) -> Bool { !(a < b) && !(b < a) }
}

/// One version's notes, from `app/release-notes/<version>.md`: the same file the GitHub release (and so Sparkle's
/// release notes link) shows. An optional front matter block marks a major release:
///
///     ---
///     big: true
///     ---
///     - A plain line per change.
///
///     ### A step title (big releases: each becomes a step in the recap)
///     - its lines
public struct ReleaseNote: Equatable, Sendable {
    public struct Section: Equatable, Sendable {
        public var title: String
        public var lines: [String]
    }

    public var version: AppVersion
    public var big: Bool
    /// The plain lines before any `###` heading.
    public var lines: [String]
    /// The `###` sections, for a big release's recap.
    public var sections: [Section]

    public init?(version: String, text: String) {
        guard let v = AppVersion(version) else { return nil }
        self.version = v
        var body = text.components(separatedBy: "\n")
        var big = false
        if body.first?.trimmingCharacters(in: .whitespaces) == "---",
           let end = body.dropFirst().firstIndex(where: { $0.trimmingCharacters(in: .whitespaces) == "---" }) {
            for line in body[1..<end] {
                let kv = line.split(separator: ":", maxSplits: 1).map { $0.trimmingCharacters(in: .whitespaces) }
                if kv.count == 2, kv[0] == "big" { big = kv[1].lowercased() == "true" }
            }
            body = Array(body[(end + 1)...])
        }
        self.big = big
        var lines: [String] = [], sections: [Section] = []
        for raw in body {
            let line = raw.trimmingCharacters(in: .whitespaces)
            if line.hasPrefix("### ") {
                sections.append(Section(title: String(line.dropFirst(4)), lines: []))
            } else if line.hasPrefix("- ") || line.hasPrefix("* ") {
                let item = String(line.dropFirst(2))
                if sections.isEmpty { lines.append(item) } else { sections[sections.count - 1].lines.append(item) }
            } else if !line.isEmpty, !line.hasPrefix("#") {
                if sections.isEmpty { lines.append(line) } else { sections[sections.count - 1].lines.append(line) }
            }
        }
        self.lines = lines
        self.sections = sections
    }

    /// Every `<version>.md` in a folder, newest first. Files that aren't a version are left out.
    public static func load(from folder: URL) -> [ReleaseNote] {
        let files = (try? FileManager.default.contentsOfDirectory(at: folder, includingPropertiesForKeys: nil)) ?? []
        return files.filter { $0.pathExtension == "md" }.compactMap { url in
            (try? String(contentsOf: url, encoding: .utf8)).flatMap {
                ReleaseNote(version: url.deletingPathExtension().lastPathComponent, text: $0)
            }
        }.sorted { $0.version > $1.version }
    }
}

/// What's New: which notes to show on this launch, and whether to remember this version as seen.
public enum WhatsNew {
    public struct Decision: Equatable, Sendable {
        public var notes: [ReleaseNote]
        /// Store the running version as the last one seen.
        public var remember: Bool
    }

    /// - firstLaunch: Runway has never been set up on this Mac. The walkthrough shows instead, and this version
    ///   counts as seen.
    /// - lastSeen nil on a Mac that has run Runway before: a version from before What's New. Show this version's
    ///   notes only.
    /// - Otherwise every version newer than the last one seen, up to and including this one, newest first.
    public static func decide(current: String, lastSeen: String?, firstLaunch: Bool,
                              notes: [ReleaseNote]) -> Decision {
        guard let now = AppVersion(current) else { return Decision(notes: [], remember: false) }
        if firstLaunch { return Decision(notes: [], remember: true) }
        let since = lastSeen.flatMap(AppVersion.init)
        if let since, since >= now { return Decision(notes: [], remember: false) }   // seen, or a downgrade
        let shown = notes.filter { note in
            note.version <= now && (since.map { note.version > $0 } ?? (note.version == now))
        }.sorted { $0.version > $1.version }
        return Decision(notes: shown, remember: true)
    }

    /// Every note up to this version, newest first: what "What's New…" in the menu reopens.
    public static func all(current: String, notes: [ReleaseNote]) -> [ReleaseNote] {
        guard let now = AppVersion(current) else { return notes }
        return notes.filter { $0.version <= now }.sorted { $0.version > $1.version }
    }
}
