import AppKit
import Foundation
import RunwayCore

/// A note at the bottom of the main window; Undo runs `runway <undo>`.
struct Toast: Equatable, Identifiable {
    let id = UUID()
    var text: String
    var undo: [String]?
    var error = false
}

/// A confirm sheet for a step that deletes something for good: what goes, what stays, and the command it runs.
struct Confirm: Identifiable {
    let id = UUID()
    var title: String
    var goes: [String]
    var stays: [String]
    var button: String
    var args: [String]
}

/// Clearing things away and the right-click menus. Every step is a `runway` command; the app only words the result.
extension AppModel {
    /// `runway <args>` and its result, for steps that need what it printed.
    func runway(_ args: [String]) async -> RunwayCLI.Result? {
        guard let cli else {
            say("Sample data: would run runway \(args.joined(separator: " "))")
            return nil
        }
        let result = await cli.run(args)
        await refresh()
        return result
    }

    func say(_ text: String, undo: [String]? = nil, error: Bool = false) {
        let toast = Toast(text: text, undo: undo, error: error)
        self.toast = toast
        Task {
            try? await Task.sleep(nanoseconds: (undo == nil ? 4 : 8) * 1_000_000_000)
            if self.toast?.id == toast.id { self.toast = nil }
        }
    }

    /// Runs the step and toasts what it said (or its error).
    private func step(_ args: [String], undo: [String]? = nil, ok: String? = nil) {
        Task {
            guard let result = await runway(args) else { return }
            let said = (result.status == 0 ? result.output : result.error)
                .trimmingCharacters(in: .whitespacesAndNewlines).replacingOccurrences(of: "runway: ", with: "")
            say(result.status == 0 ? (ok ?? said) : said, undo: result.status == 0 ? undo : nil, error: result.status != 0)
        }
    }

    func undo(_ toast: Toast) {
        guard let args = toast.undo else { return }
        self.toast = nil
        step(args, ok: "Undone")
    }

    // MARK: Right-click

    func perform(_ action: MenuAction, ticket t: Ticket) {
        switch action {
        case .discussTicket: copyPrompt(["show", t.id, "--prompt"])
        case .takeBack, .copyTakePrompt: takeBack(t.id)
        case .giveBack: step(["give", t.id])
        case .go: step(["go", t.id])
        case .no: step(["no", t.id])
        case .openPR: openPR(t)
        case .copyTicketID:
            copyQuietly(t.id)
            say("Copied \(t.id)")
        case .ticketRunsOn(let runner): step(["runs-on", t.id, runner ?? "any"])
        case .deleteTicket: confirmDelete(t)
        default: break
        }
    }

    func perform(_ action: MenuAction, repo name: String) {
        let repo = status?.repo(named: name)
        switch action {
        case .discussRepo: copyPrompt(["status", name, "--prompt"])
        case .pauseRepo: step(["pause", name], undo: ["resume", name])
        case .resumeRepo: step(["resume", name])
        case .repoRunsOn(let on): step(["runs-on", name, on.rawValue])
        case .mainComputer(let runner): step(["repo", "main", name, runner])
        case .openGitHub:
            if let slug = repo?.slug, let url = URL(string: "https://github.com/\(slug)") { NSWorkspace.shared.open(url) }
        case .revealFolder:
            if let path = repo?.path { NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: path)]) }
        case .clearDone: clearDone(name)
        case .archive: step(["repo", "archive", name], undo: ["repo", "unarchive", name], ok: "Archived \(name)")
        case .unarchive: step(["repo", "unarchive", name], ok: "\(name) is back on the board")
        case .removeRepo: confirmRemove(name)
        default: break
        }
    }

    func perform(_ action: MenuAction, runner name: String) {
        switch action {
        case .pauseRunner: step(["pause", name], undo: ["resume", name])
        case .resumeRunner: step(["resume", name])
        default: break
        }
    }

    // MARK: The steps

    /// Done tickets off the board; Undo puts back exactly those.
    func clearDone(_ repo: String) {
        Task {
            guard let result = await runway(["clear-done", repo, "--json"]) else { return }
            guard result.status == 0, let ids = try? JSONDecoder().decode([String].self, from: Data(result.output.utf8))
            else { return say(result.error.trimmingCharacters(in: .whitespacesAndNewlines), error: true) }
            if ids.isEmpty { return say("Nothing done to clear") }
            say("Cleared \(ids.count) done ticket\(ids.count == 1 ? "" : "s") (still in stats)",
                undo: ["clear-done", "--undo"] + ids)
        }
    }

    private static let snake: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    private struct RemovePreview: Decodable { var path: String; var tickets: Int; var runs: Int; var running: [String] }
    private struct DeletePreview: Decodable {
        var title: String; var runs: Int; var pr: Int?; var branch: String?; var running: Bool
    }

    func confirmRemove(_ name: String) {
        Task {
            guard let result = await runway(["repo", "remove", name, "--json"]) else { return }
            guard let p = try? Self.snake.decode(RemovePreview.self, from: Data(result.output.utf8)) else {
                return say(result.error.trimmingCharacters(in: .whitespacesAndNewlines), error: true)
            }
            if !p.running.isEmpty {
                return say("\(p.running.joined(separator: ", ")) \(p.running.count == 1 ? "is" : "are") running: "
                           + "remove \(name) when \(p.running.count == 1 ? "it finishes" : "they finish")", error: true)
            }
            confirm = Confirm(
                title: "Remove \(name) from Runway?",
                goes: ["\(p.tickets) ticket\(p.tickets == 1 ? "" : "s") and \(p.runs) run\(p.runs == 1 ? "" : "s") of history "
                       + "(logs, transcripts, reviews)", "Runway's working copies for them"],
                stays: ["Your folder, \(shortHome(p.path))", "Its branches", "Its pull requests on GitHub"],
                button: "Remove", args: ["repo", "remove", name, "--yes"])
        }
    }

    func confirmDelete(_ t: Ticket) {
        Task {
            guard let result = await runway(["delete", t.id, "--json"]) else { return }
            guard let p = try? Self.snake.decode(DeletePreview.self, from: Data(result.output.utf8)) else {
                return say(result.error.trimmingCharacters(in: .whitespacesAndNewlines), error: true)
            }
            if p.running { return say("\(t.id) is running: delete it when it finishes", error: true) }
            confirm = Confirm(
                title: "Delete \(t.id)?",
                goes: ["“\(p.title)”", "Its \(p.runs) run\(p.runs == 1 ? "" : "s") of history (logs, transcripts, reviews)"],
                stays: ["Its branch\(p.branch.map { " (\($0))" } ?? "") on GitHub"]
                    + (p.pr.map { ["Its pull request #\($0): close it on GitHub if you don't want it"] } ?? []),
                button: "Delete", args: ["delete", t.id, "--yes"])
        }
    }

    func confirmed(_ c: Confirm) {
        confirm = nil
        step(c.args)
    }

    /// A prompt from the CLI onto the clipboard, to paste into a Claude Code or Codex session.
    private func copyPrompt(_ args: [String]) {
        Task {
            guard let result = await runway(args) else { return }
            guard result.status == 0 else {
                return say(result.error.trimmingCharacters(in: .whitespacesAndNewlines), error: true)
            }
            copyQuietly(result.output.trimmingCharacters(in: .whitespacesAndNewlines))
            say("Copied. Paste it into Claude Code or Codex.")
        }
    }

    private func copyQuietly(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }

    private func shortHome(_ path: String) -> String {
        let home = ProcessInfo.processInfo.environment["HOME"] ?? NSHomeDirectory()
        return path.hasPrefix(home) ? "~" + path.dropFirst(home.count) : path
    }
}
