import Foundation

/// Everything `runway status --json` reports: the one snapshot the app draws from. The app adds no rules; anything
/// computed here is presentation (counts, grouping), never a decision.
public struct Status: Codable, Equatable, Sendable {
    public var version: Int
    public var generatedAt: Date
    /// Everything paused until this time (nil: not paused).
    public var pausedUntil: Date?
    public var repos: [Repo]
    public var runners: [Runner]
    public var agents: [Agent]
    public var tickets: [Ticket]
    public var activity: [ActivityLine]
    /// What setup has found per runner, for the first-run table.
    public var setup: [SetupRow]

    public init(version: Int = 1, generatedAt: Date, pausedUntil: Date? = nil, repos: [Repo], runners: [Runner],
                agents: [Agent], tickets: [Ticket], activity: [ActivityLine], setup: [SetupRow]) {
        self.version = version
        self.generatedAt = generatedAt
        self.pausedUntil = pausedUntil
        self.repos = repos
        self.runners = runners
        self.agents = agents
        self.tickets = tickets
        self.activity = activity
        self.setup = setup
    }

    public static func decode(_ data: Data) throws -> Status {
        try StatusCoding.decoder.decode(Status.self, from: data)
    }

    public func encoded() throws -> Data {
        try StatusCoding.encoder.encode(self)
    }

    // MARK: Presentation helpers

    public func tickets(repo: String) -> [Ticket] { tickets.filter { $0.repo == repo } }

    public func tickets(repo: String, in column: Ticket.Column) -> [Ticket] {
        tickets.filter { $0.repo == repo && $0.column == column }
    }

    /// Needs-you tickets across every repo, in the order the CLI gave them.
    public var needsYou: [Ticket] { tickets.filter { $0.column == .needsYou } }

    public func agent(_ kind: AgentKind) -> Agent? { agents.first { $0.kind == kind } }

    public func repo(named name: String) -> Repo? { repos.first { $0.name == name } }
}

public struct Repo: Codable, Equatable, Identifiable, Sendable {
    public enum State: String, Codable, Sendable { case running, idle, needsYou = "needs_you", paused, off }
    /// Any runner (the default), or only the repo's main computer.
    public enum RunsOn: String, Codable, Sendable { case any, main }

    public var name: String
    public var state: State
    /// One line under the name: "Running · 2 need you", "Paused until tomorrow".
    public var statusLine: String
    /// The runner where the repo's local folder lives.
    public var mainComputer: String
    public var runsOn: RunsOn

    public var id: String { name }

    public init(name: String, state: State, statusLine: String, mainComputer: String, runsOn: RunsOn = .any) {
        self.name = name
        self.state = state
        self.statusLine = statusLine
        self.mainComputer = mainComputer
        self.runsOn = runsOn
    }
}

public struct Runner: Codable, Equatable, Identifiable, Sendable {
    public enum Kind: String, Codable, Sendable { case thisMac = "this_mac", sshMac = "ssh_mac", cloud }
    public enum State: String, Codable, Sendable { case online, asleep, offline }

    public var name: String
    public var kind: Kind
    public var slotsUsed: Int
    public var slotsTotal: Int
    public var state: State

    public var id: String { name }

    public init(name: String, kind: Kind, slotsUsed: Int, slotsTotal: Int, state: State) {
        self.name = name
        self.kind = kind
        self.slotsUsed = slotsUsed
        self.slotsTotal = slotsTotal
        self.state = state
    }

    /// "1 of 2", or the state when the runner can't take work.
    public var load: String { state == .online ? "\(slotsUsed) of \(slotsTotal)" : state.rawValue }
}

public enum AgentKind: String, Codable, Sendable, CaseIterable { case claude, codex }

public struct Agent: Codable, Equatable, Identifiable, Sendable {
    public var kind: AgentKind
    /// Set while the agent's usage limit holds; nil means available.
    public var restingUntil: Date?

    public var id: AgentKind { kind }
    public var available: Bool { restingUntil == nil }

    public init(kind: AgentKind, restingUntil: Date? = nil) {
        self.kind = kind
        self.restingUntil = restingUntil
    }
}

public struct Ticket: Codable, Equatable, Identifiable, Sendable {
    public enum Column: String, Codable, Sendable, CaseIterable {
        case needsYou = "needs_you", upNext = "up_next", running, done
    }
    public enum AgentChoice: String, Codable, Sendable { case claude, codex, any }
    public enum Risk: String, Codable, Sendable { case low, notLow = "not_low" }
    public enum Stage: String, Codable, Sendable, CaseIterable { case build, check, review, merge }

    /// A needs-you question with the two answers the person can give.
    public struct Question: Codable, Equatable, Sendable {
        public var text: String
        /// The menu-sized form, for the menu bar and the side panel: "Merge sign-in change?".
        public var short: String?
        public var goLabel: String
        public var noLabel: String

        public init(text: String, short: String? = nil, goLabel: String = "Go", noLabel: String = "No") {
            self.text = text
            self.short = short
            self.goLabel = goLabel
            self.noLabel = noLabel
        }
    }

    public var id: String
    public var repo: String
    public var title: String
    public var column: Column
    public var agent: AgentChoice
    public var risk: Risk
    /// The runner it runs or ran on; nil while it waits for any free runner.
    public var runsOn: String?
    /// True when the ticket waits for `runsOn` even if other runners are free.
    public var pinned: Bool
    /// Only for running tickets.
    public var stage: Stage?
    public var pr: String?
    /// The PR's web address, when the repo is on GitHub.
    public var prUrl: String?
    public var review: String?
    public var question: Question?
    /// Where it was filed from: "Claude Code on this Mac".
    public var filedFrom: String
    public var filedAt: Date
    public var waitsOn: [String]
    /// Seconds since the current run started (running tickets).
    public var elapsed: Int?
    /// One line the inspector shows under the fields.
    public var summary: String?

    public init(id: String, repo: String, title: String, column: Column, agent: AgentChoice, risk: Risk,
                runsOn: String? = nil, pinned: Bool = false, stage: Stage? = nil, pr: String? = nil,
                prUrl: String? = nil, review: String? = nil, question: Question? = nil, filedFrom: String, filedAt: Date,
                waitsOn: [String] = [], elapsed: Int? = nil, summary: String? = nil) {
        self.id = id
        self.repo = repo
        self.title = title
        self.column = column
        self.agent = agent
        self.risk = risk
        self.runsOn = runsOn
        self.pinned = pinned
        self.stage = stage
        self.pr = pr
        self.prUrl = prUrl
        self.review = review
        self.question = question
        self.filedFrom = filedFrom
        self.filedAt = filedAt
        self.waitsOn = waitsOn
        self.elapsed = elapsed
        self.summary = summary
    }

    /// What the card's second line says about where it runs.
    public var placeLine: String {
        guard let runsOn else { return "next free runner" }
        return pinned ? "\(runsOn) (pinned)" : runsOn
    }
}

public struct ActivityLine: Codable, Equatable, Identifiable, Sendable {
    public enum Kind: String, Codable, Sendable {
        case filed, start, review, merged, needsYou = "needs_you", limit, failed, setup, answer, other

        /// A kind this build doesn't know shows as `other`, so one new event never blanks the whole status.
        public init(from decoder: Decoder) throws {
            let raw = try decoder.singleValueContainer().decode(String.self)
            self = Kind(rawValue: raw) ?? .other
        }
    }

    public var at: Date
    public var kind: Kind
    public var text: String
    public var repo: String?

    public var id: String { "\(at.timeIntervalSince1970)-\(kind.rawValue)-\(text)" }

    public init(at: Date, kind: Kind, text: String, repo: String? = nil) {
        self.at = at
        self.kind = kind
        self.text = text
        self.repo = repo
    }
}

/// One row of the first-run table: what setup has found on a runner.
public struct SetupRow: Codable, Equatable, Identifiable, Sendable {
    public enum Check: String, Codable, Sendable { case yes, checking, signIn = "sign_in", no }

    public var runner: String
    public var reachable: Check
    public var claude: Check
    public var codex: Check
    public var github: Check

    public var id: String { runner }

    public init(runner: String, reachable: Check, claude: Check, codex: Check, github: Check) {
        self.runner = runner
        self.reachable = reachable
        self.claude = claude
        self.codex = codex
        self.github = github
    }
}

enum StatusCoding {
    /// ISO 8601 with a zone, or a local wall-clock time without one (sample data reads the same everywhere).
    static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        decoder.dateDecodingStrategy = .custom { decoder in
            let text = try decoder.singleValueContainer().decode(String.self)
            if let date = parse(text) { return date }
            throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath,
                                                    debugDescription: "Not a date: \(text)"))
        }
        return decoder
    }()

    static let encoder: JSONEncoder = {
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        encoder.dateEncodingStrategy = .iso8601
        encoder.outputFormatting = [.prettyPrinted, .sortedKeys]
        return encoder
    }()

    static func parse(_ text: String) -> Date? {
        let zoned = ISO8601DateFormatter()
        if let date = zoned.date(from: text) { return date }
        let local = DateFormatter()
        local.locale = Locale(identifier: "en_US_POSIX")
        local.timeZone = .current
        local.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
        return local.date(from: text)
    }
}
