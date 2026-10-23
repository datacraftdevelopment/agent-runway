import Foundation
import Observation
import os
import RunwayCore

/// The app's state: the latest status snapshot and what the person has selected. Buttons call `act`, which for now
/// only logs; in Phase 2 each one runs a `runway` command and the next status read shows the result.
@MainActor
@Observable
final class AppModel {
    enum Tab: Hashable { case board, activity }

    private(set) var status: Status?
    private(set) var loadError: String?
    var selectedRepo: String?
    var selectedTicket: String?
    var tab: Tab = .board
    /// The last action a no-op button logged, shown in the status bar line so a click visibly does something.
    private(set) var lastAction: String?

    private let logger = Logger(subsystem: "dev.datacraft.runway-agent", category: "actions")

    init() {
        // RUNWAY_TAB=activity and RUNWAY_SELECT=<ticket> open the window in a given state, for screenshots.
        if ProcessInfo.processInfo.environment["RUNWAY_TAB"] == "activity" { tab = .activity }
        load()
    }

    func load() {
        guard let url = Self.statusURL() else {
            loadError = "No status file found (set RUNWAY_STATUS_FILE)"
            return
        }
        do {
            let status = try Status.decode(Data(contentsOf: url))
            self.status = status
            loadError = nil
            if selectedRepo == nil { selectedRepo = status.repos.first?.name }
            if selectedTicket == nil { selectedTicket = Self.defaultTicket(status, repo: selectedRepo) }
        } catch {
            loadError = "Couldn't read \(url.lastPathComponent): \(error.localizedDescription)"
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

    func act(_ what: String) {
        logger.info("\(what, privacy: .public)")
        print("runway action: \(what)")
        lastAction = what
    }

    /// The first needs-you ticket, else T-19 as in the mock, else the first ticket in the repo.
    private static func defaultTicket(_ status: Status, repo: String?) -> String? {
        guard let repo else { return nil }
        let tickets = status.tickets(repo: repo)
        if let pick = ProcessInfo.processInfo.environment["RUNWAY_SELECT"], tickets.contains(where: { $0.id == pick }) {
            return pick
        }
        return tickets.first { $0.id == "T-19" }?.id ?? tickets.first?.id
    }

    /// `RUNWAY_STATUS_FILE`, else the copy inside Runway.app, else the test fixture when run from the package.
    static func statusURL() -> URL? {
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
