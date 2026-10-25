import Foundation

/// The first-run walkthrough's rules, kept out of the view so they test without a window: which step to open on,
/// whether the walkthrough is needed at all on this launch, and what "Set it up" installs.
public enum SetupGuide {
    public enum Step: Int, CaseIterable, Sendable {
        case welcome, check, install, next

        public var title: String {
            switch self {
            case .welcome: return "Welcome"
            case .check: return "Check this Mac"
            case .install: return "Set it up"
            case .next: return "Next"
            }
        }
    }

    /// Something to put in place, shown before "Set it up" and ticked as it lands.
    public struct Item: Equatable, Identifiable, Sendable {
        public enum Kind: String, Sendable { case database, command, skills }
        public var kind: Kind
        public var title: String
        public var detail: String
        public var done: Bool
        /// Not installed, and nothing to install it into (no engine yet), so "Set it up" skips it.
        public var skipped: Bool
        public var id: String { kind.rawValue }
    }

    /// Whether this Mac has what Runway needs to run tickets: one engine signed in, git, gh signed in, tmux.
    public static func macReady(_ report: SetupReport) -> Bool { report.ready }

    /// Whether to show the walkthrough on this launch. The app re-checks on every launch and only shows it again when
    /// something is missing. The Terminal link is optional, so it never brings the walkthrough back on its own.
    public static func needed(_ report: SetupReport) -> Bool {
        report.databaseExists == false || !report.ready || report.skills.installed != true || report.repos.isEmpty
    }

    /// Where to open: the welcome on the very first launch, else the first step with something missing.
    public static func start(_ report: SetupReport?, firstLaunch: Bool) -> Step {
        if firstLaunch { return .welcome }
        guard let report else { return .check }
        if !report.ready { return .check }
        if report.databaseExists == false || report.skills.installed != true { return .install }
        return .next
    }

    /// What "Set it up" puts in place, in order, and what is already there.
    public static func items(_ report: SetupReport) -> [Item] {
        // The skills go into each engine that is installed; installing them needs no sign-in.
        let engines = report.tools.filter { ($0.name == "claude" || $0.name == "codex") && $0.ok }
            .map { $0.name == "codex" ? "Codex" : "Claude Code" }
        let into = engines.isEmpty ? "Claude Code or Codex" : engines.joined(separator: " and ")
        return [
            Item(kind: .database, title: "Runway's folder and database",
                 detail: "~/.runway: your tickets, runs and their logs. Nothing of Runway's goes into your repos.",
                 done: report.databaseExists != false, skipped: false),
            Item(kind: .command, title: "The runway command in Terminal",
                 detail: "One link in ~/.local/bin to the command inside this app, so your agent can file tickets. "
                    + "It never replaces a file that's already there.",
                 done: report.command.linked, skipped: false),
            Item(kind: .skills, title: "The Agent Runway skills in \(into)",
                 detail: "Added with \(into == "Codex" ? "Codex's" : "each agent's") own plugin command. "
                    + "Remove them the same way.",
                 done: report.skills.installed == true,
                 skipped: report.skills.installed != true && (engines.isEmpty || !report.skills.built)),
        ]
    }

    /// The first prompt to paste into a normal Claude Code or Codex session in the watched repo.
    public static func firstPrompt(repo: String?) -> String {
        "I'd like to work on " + (repo.map { "\($0): " } ?? "this repo: ")
            + "<describe the change>. Ask me what you need to, write a short spec with its acceptance checks, "
            + "then use the file-tickets skill to file it as Runway tickets."
    }
}
