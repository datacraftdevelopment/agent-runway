import AppKit
import Foundation
import Observation
import os
import RunwayCore

/// The app's state: the latest status snapshot and what the person has selected. It holds no rules: it reads
/// `runway status --json` every few seconds and every button runs a `runway` command, then reads the status again.
/// With no `runway` command found (or `RUNWAY_STATUS_FILE` set) it shows a status file instead, read-only.
@MainActor
@Observable
final class AppModel {
    enum Tab: Hashable { case board, activity, stats }
    enum Source: Equatable { case live, sample }

    private(set) var status: Status?
    /// `runway stats --json`, read less often than the status.
    private(set) var stats: StatsSnapshot?
    var statsDays = 7
    private(set) var loadError: String?
    private(set) var source: Source = .sample
    var selectedRepo: String?
    var selectedTicket: String?
    var tab: Tab = .board
    /// The last thing a button did (or the error it got), shown in the toolbar.
    private(set) var lastAction: String?

    let cli: RunwayCLI?
    private var loop: Process?
    private var polling: Task<Void, Never>?
    private let logger = Logger(subsystem: "dev.datacraft.runway-agent", category: "actions")

    init() {
        let env = ProcessInfo.processInfo.environment
        // RUNWAY_TAB=activity and RUNWAY_SELECT=<ticket> open the window in a given state, for screenshots.
        if env["RUNWAY_TAB"] == "activity" { tab = .activity }
        if env["RUNWAY_TAB"] == "stats" { tab = .stats }
        cli = env["RUNWAY_STATUS_FILE"] == nil ? RunwayCLI.find() : nil
        if let cli {
            source = .live
            // First launch ever: nothing runs until the walkthrough's "Set it up" has made ~/.runway (startLive).
            firstLaunch = !FileManager.default.fileExists(atPath: Self.databasePath)
            if firstLaunch {
                if RenderMode.folder != nil { Task { [weak self] in if let self { await RenderMode.renderAndQuit(self) } } }
            } else {
                startLive(cli)
            }
        } else {
            loadSample()
            if RenderMode.folder != nil {
                Task { [weak self] in if let self { await RenderMode.renderAndQuit(self) } }
            }
        }
    }

    /// The loop and the status polling, once Runway's database exists.
    func startLive(_ cli: RunwayCLI) {
        guard polling == nil else { return }
        if ProcessInfo.processInfo.environment["RUNWAY_NO_LOOP"] == nil { startLoop(cli) }
        do {
            polling = Task { [weak self] in
                var tick = 0
                while !Task.isCancelled {
                    await self?.refresh()
                    if tick % 5 == 0 { await self?.refreshStats() }
                    tick += 1
                    if let self, RenderMode.folder != nil { return await RenderMode.renderAndQuit(self) }
                    try? await Task.sleep(nanoseconds: 3_000_000_000)
                }
            }
        }
    }

    // MARK: Reading

    func refresh() async {
        guard let cli else { return }
        let result = await cli.run(["status", "--json"])
        guard result.status == 0 else {
            loadError = "runway status failed: \(result.error.trimmingCharacters(in: .whitespacesAndNewlines))"
            return
        }
        do {
            apply(try Status.decode(Data(result.output.utf8)))
        } catch {
            loadError = "Couldn't read runway status: \(error.localizedDescription)"
        }
    }

    func refreshStats() async {
        guard let cli else { return }
        let result = await cli.run(["stats", "--json"])
        if result.status == 0, let snap = try? StatsSnapshot.decode(Data(result.output.utf8)) { stats = snap }
    }

    private func loadSample() {
        guard let url = Self.sampleURL() else {
            loadError = "No runway command and no status file found"
            return
        }
        do {
            apply(try Status.decode(Data(contentsOf: url)))
        } catch {
            loadError = "Couldn't read \(url.lastPathComponent): \(error.localizedDescription)"
        }
    }

    private func apply(_ status: Status) {
        if status != self.status { self.status = status }
        loadError = nil
        if selectedRepo == nil || status.repo(named: selectedRepo ?? "") == nil { selectedRepo = status.repos.first?.name }
        if selectedTicket == nil || !status.tickets.contains(where: { $0.id == selectedTicket }) {
            selectedTicket = Self.defaultTicket(status, repo: selectedRepo)
        }
    }

    var repo: Repo? { selectedRepo.flatMap { status?.repo(named: $0) } }

    var ticket: Ticket? {
        guard let status, let selectedTicket else { return nil }
        return status.tickets.first { $0.id == selectedTicket }
    }

    func select(repo: String) {
        selectedRepo = repo
        if let status, ticket?.repo != repo { selectedTicket = Self.defaultTicket(status, repo: repo) }
    }

    // MARK: Acting

    /// Runs `runway <args>`, shows what it said, and reads the status again.
    func run(_ args: [String]) {
        logger.info("runway \(args.joined(separator: " "), privacy: .public)")
        guard let cli else {
            lastAction = "Sample data: would run runway \(args.joined(separator: " "))"
            return
        }
        lastAction = "runway \(args.joined(separator: " "))…"
        Task {
            let result = await cli.run(args)
            let said = (result.status == 0 ? result.output : result.error).trimmingCharacters(in: .whitespacesAndNewlines)
            lastAction = said.isEmpty ? "runway \(args.first ?? "") done" : String(said.prefix(200))
            await refresh()
        }
    }

    /// A button that has nothing to run yet: say so rather than do nothing.
    func act(_ what: String) {
        logger.info("\(what, privacy: .public)")
        lastAction = what
    }

    // MARK: First run

    /// The last `runway doctor --json`, and whether a check is running.
    var setup: SetupReport?
    var checking = false
    /// A folder the person picked as their first repo, with what Runway guessed about it.
    var pendingRepo: RepoSuggestion?
    var pendingCheck = ""
    var setupMessage: String?

    // The walkthrough (AppModel+Guide.swift).
    /// Runway had never been set up on this Mac when the app started: no ~/.runway database.
    private(set) var firstLaunch = false
    var guideStep: SetupGuide.Step = .welcome
    /// "Set it up": the items running now, done this session, and any that failed with what they said.
    var installing: SetupGuide.Item.Kind?
    var installed: Set<SetupGuide.Item.Kind> = []
    var installErrors: [SetupGuide.Item.Kind: String] = [:]
    /// The prompt last copied from the Next step, so the button can say so.
    var copiedPrompt = false

    // What's New (AppModel+Guide.swift).
    var whatsNew: [ReleaseNote] = []
    var updatingSkills = false

    func runDoctor() {
        guard let cli else { return setupMessage = "Sample data: no runway command to check with" }
        checking = true
        Task {
            let result = await cli.run(["doctor", "--json"])
            checking = false
            if let report = try? SetupReport.decode(Data(result.output.utf8)) {
                setup = report
                setupMessage = nil
            } else {
                setupMessage = "The check didn't finish: " + (result.error.isEmpty ? "no report" : result.error)
            }
            await refresh()
        }
    }

    /// Asks first: the link is the one thing first run writes outside the app and ~/.runway.
    func installCommand() {
        guard let cli, let setup else { return }
        let alert = NSAlert()
        alert.messageText = "Make runway available in Terminal?"
        alert.informativeText = "Runway adds one link, \(setup.command.link), pointing at the runway command inside "
            + "this app. Nothing else is changed, and nothing is replaced: if a file is already there, Runway stops "
            + "and says so."
            + (setup.command.linkDirOnPath ? "" : "\n\nThat folder isn't on your PATH yet; Runway will show the line "
               + "that adds it.")
        alert.addButton(withTitle: "Add the link")
        alert.addButton(withTitle: "Not now")
        NSApplication.shared.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        Task {
            let result = await cli.run(["install-command"])
            setupMessage = (result.status == 0 ? result.output : result.error).trimmingCharacters(in: .whitespacesAndNewlines)
            runDoctor()
        }
    }

    /// Asks first: installing the skills changes Claude Code's and Codex's own plugin settings.
    func installSkills() {
        guard let cli else { return }
        let alert = NSAlert()
        alert.messageText = "Add Runway's skills to Claude Code and Codex?"
        alert.informativeText = "Runway adds its plugin, agent-runway (map, grill, prototype, spec, file-tickets, runway, setup, take-back), through each "
            + "agent's own plugin commands: claude plugin install and codex plugin add, from the copy inside this app. "
            + "You can remove it the same way (claude plugin uninstall / codex plugin remove)."
        alert.addButton(withTitle: "Add the skills")
        alert.addButton(withTitle: "Not now")
        NSApplication.shared.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        setupMessage = "Adding the skills…"
        Task {
            let result = await cli.run(["install-skills"])
            setupMessage = (result.status == 0 ? result.output : result.error).trimmingCharacters(in: .whitespacesAndNewlines)
            runDoctor()
        }
    }

    /// A folder picker for the first repo; Runway then guesses its name, GitHub repo and check command.
    func chooseRepo() {
        guard let cli else { return }
        let panel = NSOpenPanel()
        panel.canChooseDirectories = true
        panel.canChooseFiles = false
        panel.allowsMultipleSelection = false
        panel.prompt = "Choose"
        panel.message = "Pick the local clone of a GitHub repo for Runway to work on."
        NSApplication.shared.activate(ignoringOtherApps: true)
        guard panel.runModal() == .OK, let url = panel.url else { return }
        chooseRepo(at: url.path)
    }

    func chooseRepo(at path: String) {
        guard let cli else { return }
        Task {
            let result = await cli.run(["repo", "suggest-check", path])
            guard let suggestion = try? RepoSuggestion.decode(Data(result.output.utf8)) else {
                setupMessage = "Couldn't read that folder: \(result.error)"
                return
            }
            pendingRepo = suggestion
            pendingCheck = suggestion.check ?? ""
            setupMessage = nil
        }
    }

    func addPendingRepo() {
        guard let cli, let repo = pendingRepo else { return }
        var args = ["repo", "add", repo.path]
        let check = pendingCheck.trimmingCharacters(in: .whitespaces)
        if !check.isEmpty { args += ["--check", check] }
        Task {
            let result = await cli.run(args)
            setupMessage = (result.status == 0 ? result.output : result.error).trimmingCharacters(in: .whitespacesAndNewlines)
            if result.status == 0 {
                pendingRepo = nil
                select(repo: repo.name)
            }
            runDoctor()
        }
    }

    func copy(_ text: String) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
        setupMessage = "Copied: \(text)"
    }

    // Clearing things away and the context menus (AppModel+Tidy.swift).
    /// A short note at the bottom of the window, with Undo when the step can be undone.
    var toast: Toast?
    /// A confirm sheet for a step that deletes: what goes and what stays.
    var confirm: Confirm?

    /// Take-back prompts copied this session, by ticket, shown in the inspector.
    private(set) var takePrompts: [String: String] = [:]

    /// `runway take` (stops the worker, keeps the branch, marks it taken back; harmless twice), then the prompt from
    /// `runway take --prompt` onto the clipboard. Nothing is launched or resumed.
    func takeBack(_ ticket: String) {
        guard let cli else { return act("Sample data: nothing to take back") }
        Task {
            let took = await cli.run(["take", ticket])
            guard took.status == 0 else {
                lastAction = took.error.trimmingCharacters(in: .whitespacesAndNewlines)
                return
            }
            let prompt = await cli.run(["take", ticket, "--prompt"])
            let text = prompt.output.trimmingCharacters(in: .whitespacesAndNewlines)
            NSPasteboard.general.clearContents()
            NSPasteboard.general.setString(text, forType: .string)
            takePrompts[ticket] = text
            lastAction = "\(ticket) taken back; prompt copied"
            await refresh()
        }
    }

    func openPR(_ ticket: Ticket) {
        guard let url = ticket.prUrl.flatMap(URL.init(string:)) else { return act("No PR link for \(ticket.id)") }
        NSWorkspace.shared.open(url)
    }

    // MARK: The loop

    private func startLoop(_ cli: RunwayCLI) {
        let log = FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent(".runway/loop.log")
        try? FileManager.default.createDirectory(at: log.deletingLastPathComponent(), withIntermediateDirectories: true)
        loop = cli.startLoop(log: log)
        NotificationCenter.default.addObserver(forName: NSApplication.willTerminateNotification, object: nil,
                                               queue: .main) { [weak self] _ in
            MainActor.assumeIsolated { self?.loop?.terminate() }
        }
    }

    var loopRunning: Bool { loop?.isRunning ?? false }

    // MARK: Helpers

    /// The first needs-you ticket, else T-19 as in the mock, else the first ticket in the repo.
    private static func defaultTicket(_ status: Status, repo: String?) -> String? {
        guard let repo else { return nil }
        let tickets = status.tickets(repo: repo)
        if let pick = ProcessInfo.processInfo.environment["RUNWAY_SELECT"], tickets.contains(where: { $0.id == pick }) {
            return pick
        }
        return tickets.first { $0.column == .needsYou }?.id ?? tickets.first { $0.id == "T-19" }?.id ?? tickets.first?.id
    }

    /// `RUNWAY_STATUS_FILE`, else the sample inside Runway.app, else the test fixture when run from the package.
    static func sampleURL() -> URL? {
        let fm = FileManager.default
        if let path = ProcessInfo.processInfo.environment["RUNWAY_STATUS_FILE"], fm.fileExists(atPath: path) {
            return URL(fileURLWithPath: path)
        }
        if let bundled = Bundle.main.url(forResource: "sample-status", withExtension: "json") { return bundled }
        var dir = Bundle.main.executableURL?.deletingLastPathComponent()
        while let current = dir, current.path != "/" {
            let fixture = current.appendingPathComponent("Tests/RunwayCoreTests/Fixtures/sample-status.json")
            if fm.fileExists(atPath: fixture.path) { return fixture }
            dir = current.deletingLastPathComponent()
        }
        return nil
    }
}
