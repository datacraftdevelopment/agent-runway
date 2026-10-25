import Foundation

/// What `runway doctor --json` reports for first run: the command, the database, each tool and sign-in with the line
/// that fixes it, whether the skills exist yet, and the repos already watched.
public struct SetupReport: Codable, Equatable, Sendable {
    public struct Command: Codable, Equatable, Sendable {
        public var path: String
        public var link: String
        public var linked: Bool
        public var linkDirOnPath: Bool
    }

    public struct Tool: Codable, Equatable, Identifiable, Sendable {
        public var name: String
        public var ok: Bool
        public var path: String?
        public var why: String
        public var fix: String?
        /// The engine this Mac doesn't use, while the other one is ready: shown as optional, never as a failure.
        public var optional: Bool?
        public var id: String { name }
    }

    public struct SignIn: Codable, Equatable, Identifiable, Sendable {
        public var name: String
        public var label: String
        public var ok: Bool
        public var fix: String?
        public var optional: Bool?
        public var id: String { name }
    }

    public struct Skills: Codable, Equatable, Sendable {
        /// This copy of Runway carries the skills.
        public var built: Bool
        /// Installed in Claude Code / Codex, as their own plugin lists say.
        public var claude: Bool?
        public var codex: Bool?
        public var note: String
        /// In every engine this Mac has (one engine is enough).
        public var installed: Bool?
    }

    public var command: Command
    public var database: String
    /// Whether ~/.runway's database is there yet. `runway doctor` only looks; `runway init` makes it. Nil from a
    /// runway too old to say.
    public var databaseExists: Bool?
    public var tools: [Tool]
    public var signins: [SignIn]
    /// The engines that are ready: Claude Code, Codex, or both. One is enough.
    public var engines: [String]?
    public var skills: Skills
    public var repos: [String]
    public var ready: Bool

    public static func decode(_ data: Data) throws -> SetupReport {
        try StatusCoding.decoder.decode(SetupReport.self, from: data)
    }
}

/// What `runway repo suggest-check --json` says about a folder the person picked.
public struct RepoSuggestion: Codable, Equatable, Sendable {
    public var path: String
    public var name: String
    public var git: Bool
    public var slug: String?
    public var check: String?

    public static func decode(_ data: Data) throws -> RepoSuggestion {
        try StatusCoding.decoder.decode(RepoSuggestion.self, from: data)
    }
}
