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
    /// Archived repos: off the board, restorable. Nil from a runway too old to archive.
    public var archived: [ArchivedRepo]? = nil
    /// Whether Runway's loop (the thing that starts tickets) is alive. Nil from an older runway.
    public var loopRunning: Bool? = nil

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
    /// owner/name on GitHub, and the local clone (nil from an older runway).
    public var slug: String? = nil
    public var path: String? = nil
    /// With tickets up next and none running: why nothing starts ("Nothing can run: 4 tickets wait on T-4, which
    /// needs you"), and the ticket to look at. Nil while something runs or the next tick will start one.
    public var idleReason: String? = nil
    public var idleTicket: String? = nil
    /// The check command that applies, and where it's set: "runway.json" on the base branch, "runway" (kept in
    /// Runway), or nil when there is none and sessions can't run the repo's tests.
    public var checkCmd: String? = nil
    public var checkFrom: String? = nil

    /// The reason without its "Nothing can run: " lead, for the menu and the side panel.
    public var idleShort: String? { idleReason?.replacingOccurrences(of: "Nothing can run: ", with: "") }

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
    /// Paused by the person until then (nil: not paused, or an older runway).
    public var pausedUntil: Date? = nil
    /// Its last reading and whether it's holding new work back (nil from an older runway).
    public var load: Load? = nil

    public struct Load: Codable, Equatable, Sendable {
        public var sessionsRunning: Int
        public var sessionsMax: Int
        public var hold: String?
        public var summary: String
        public var availableMb: Int?
        public var memoryLevel: Int?
        public var loadRatio: Double?
        public var cpuUsedPct: Int? = nil
        public var diskFreeGb: Double?
    }

    /// "2 of 3 · memory ok", or "holding: busy (memory)" while it's holding new work back.
    public var loadLine: String {
        guard state == .online else { return state.rawValue }
        if pausedUntil != nil { return "paused" }
        guard let load else { return load_ }
        if let hold = load.hold { return "holding: \(hold)" }
        return "\(load.sessionsRunning) of \(load.sessionsMax) · \(load.summary)"
    }

    /// "1 of 2": an older runway sends no reading.
    private var load_: String { "\(slotsUsed) of \(slotsTotal)" }

    public var id: String { name }

    public init(name: String, kind: Kind, slotsUsed: Int, slotsTotal: Int, state: State) {
        self.name = name
        self.kind = kind
        self.slotsUsed = slotsUsed
        self.slotsTotal = slotsTotal
        self.state = state
    }

}

/// A repo taken off the board with `runway repo archive`, and how many tickets it keeps.
public struct ArchivedRepo: Codable, Equatable, Identifiable, Sendable {
    public var name: String
    public var tickets: Int
    public var id: String { name }

    public init(name: String, tickets: Int) {
        self.name = name
        self.tickets = tickets
    }
}

/// "45 s", "12 min", "1 h 5 min", "1 d 3 h": the same words `runway show` uses.
public enum Duration {
    public static func words(_ seconds: Double) -> String {
        let s = max(0, Int(seconds))
        if s < 60 { return "\(s) s" }
        let m = s / 60
        if m < 60 { return "\(m) min" }
        let (h, mm) = (m / 60, m % 60)
        if h < 24 { return mm > 0 ? "\(h) h \(mm) min" : "\(h) h" }
        let (d, hh) = (h / 24, h % 24)
        return hh > 0 ? "\(d) d \(hh) h" : "\(d) d"
    }
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
    /// The code review's verdict (two fresh sessions review each build: code and function).
    public var review: String?
    public var functionReview: String?
    /// Taken back by the person: waits in Needs you until given back.
    public var taken: Bool?
    /// Hours since it was taken back; the board nudges after a day.
    public var takenHours: Double?
    /// Taken back: when its worktree last changed (newest commit or edited file), so the board shows work going on.
    public var lastActivity: Date?

    /// Taken back more than a day ago: a quiet nudge that it is still waiting to be given back, done or dropped.
    public var takenLong: Bool { taken == true && (takenHours ?? 0) >= 24 }
    /// "work", or "retro" for a ticket Runway filed itself after repeated stops.
    public var kind: String?
    /// For a retro: the failing runs behind it.
    public var retroRuns: [RetroRun]?

    public struct RetroRun: Codable, Equatable, Sendable {
        public var ticket: String
        public var title: String
        public var prUrl: String?
        public var record: String?
    }
    public var question: Question?
    /// Where it was filed from: "Claude Code on this Mac".
    public var filedFrom: String
    public var filedAt: Date
    public var waitsOn: [String]
    /// Each open blocker with where it is and what holds it in turn; the open tickets this one blocks; and why the
    /// loop isn't starting it although it's ready (its touches overlap a running ticket, or its Mac is busy).
    public var blockedBy: [Blocker]? = nil
    /// The person does it in their own session (a device, the simulator, how it feels); the loop never starts it.
    public var handsOn: Bool? = nil
    /// Finished by hand with `runway done`: no PR of Runway's.
    public var doneLocally: Bool? = nil

    /// Up next and the person's to do by hand.
    public var yoursToDo: Bool { handsOn == true && column == .upNext }
    public var blocks: [String]? = nil
    public var hold: String? = nil
    /// When it started, finished, entered its current stage or began waiting, and seconds per part. Nil from an
    /// older runway.
    public var timing: Timing? = nil

    public struct Timing: Codable, Equatable, Sendable {
        public var startedAt: Date?
        public var finishedAt: Date?
        public var stage: String?
        public var stageStartedAt: Date?
        public var waitingSince: Date?
        public var totalSeconds: Int?
        public var parts: [String: Int]?
        public var runs: [RunTime]?

        public struct RunTime: Codable, Equatable, Sendable {
            public var kind: String
            public var role: String?
            public var agent: String
            public var seconds: Int
        }
    }

    /// The card's timer line at `now`: "Building · 12 min · 38 min in all", "Waiting 1 h", "Waiting for you 20 min",
    /// "Took 1 h 12 min". Nil when there's nothing to time.
    public func timerLine(now: Date) -> String? {
        guard let t = timing else { return nil }
        switch column {
        case .running:
            guard let start = t.startedAt else { return nil }
            let stage = (t.stage ?? "running").replacingOccurrences(of: "_", with: " ")
            let label = stage.prefix(1).uppercased() + stage.dropFirst()
            let inStage = t.stageStartedAt.map { Duration.words(now.timeIntervalSince($0)) }
            return [inStage.map { "\(label) · \($0)" } ?? String(label),
                    "\(Duration.words(now.timeIntervalSince(start))) in all"].joined(separator: " · ")
        case .upNext:
            return t.waitingSince.map { "Waiting \(Duration.words(now.timeIntervalSince($0)))" }
        case .needsYou:
            if taken == true {
                let since = t.waitingSince.map { " · \(Duration.words(now.timeIntervalSince($0)))" } ?? ""
                let last = lastActivity.map { " · last activity \(Duration.words(max(0, now.timeIntervalSince($0)))) ago" }
                return "Taken back by you" + since + (last ?? "")
            }
            return t.waitingSince.map { "Waiting for you \(Duration.words(now.timeIntervalSince($0)))" }
        case .done:
            return t.totalSeconds.map { "Took \(Duration.words(Double($0)))" }
        }
    }

    /// Held only because its Mac is short of memory, CPU or disk: "Start anyway" can skip that check once.
    public var heldForCapacity: Bool { column == .upNext && (hold?.contains(" is busy (") ?? false) }

    public struct Blocker: Codable, Equatable, Sendable {
        public var id: String
        public var title: String?
        public var column: Column?
        public var waitsOn: [String]
        public var handsOn: Bool? = nil
    }
    /// Seconds since the current run started (running tickets).
    public var elapsed: Int?
    /// One line the inspector shows under the fields.
    public var summary: String?

    public init(id: String, repo: String, title: String, column: Column, agent: AgentChoice, risk: Risk,
                runsOn: String? = nil, pinned: Bool = false, stage: Stage? = nil, pr: String? = nil,
                prUrl: String? = nil, review: String? = nil, functionReview: String? = nil, question: Question? = nil, filedFrom: String, filedAt: Date,
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
        self.functionReview = functionReview
        self.question = question
        self.filedFrom = filedFrom
        self.filedAt = filedAt
        self.waitsOn = waitsOn
        self.elapsed = elapsed
        self.summary = summary
    }

    /// What the card's second line says about where it runs.
    public var placeLine: String {
        if doneLocally == true && column == .done { return "done by hand" }
        if handsOn == true && column == .upNext { return "yours, by hand" }
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
    public enum Check: String, Codable, Sendable { case yes, checking, signIn = "sign_in", no, optional }

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
