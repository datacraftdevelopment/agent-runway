import Foundation

/// What `runway stats --json` reports: how hands-off Runway is, for all repos and each one, over 7 and 30 days.
public struct StatsSnapshot: Codable, Equatable, Sendable {
    public struct Scope: Codable, Equatable, Sendable {
        public var repo: String?
        public var windows: [Window]
        public var waiting: [Waiting]

        public func window(_ days: Int) -> Window? { windows.first { $0.days == days } }
    }

    public struct Window: Codable, Equatable, Sendable {
        public var days: Int
        public var merged: Int
        public var handsOff: Int
        public var handsOffRate: Double?
        public var handsOffTickets: [String]
        public var otherTickets: [String]
        public var cycleMinutes: Cycle
        public var costPerTicket: Cost
        public var stopped: [Stop]
    }

    public struct Cycle: Codable, Equatable, Sendable {
        public var handsOff: Double?
        public var rest: Double?
    }

    public struct Cost: Codable, Equatable, Sendable {
        public var medianUsd: Double?
        public var medianTokens: Int?
        public var byAgent: [AgentCost]
    }

    /// Dollars only when the engine reported them (Claude Code); tokens always. Never an estimate.
    public struct AgentCost: Codable, Equatable, Sendable {
        public var agent: AgentKind
        public var tickets: Int
        public var medianUsd: Double?
        public var medianTokens: Int?
    }

    public struct Stop: Codable, Equatable, Sendable {
        public var reason: String
        public var label: String
        public var count: Int
    }

    public struct Waiting: Codable, Equatable, Sendable {
        public var id: String
        public var repo: String
        public var title: String
        public var reason: String
        public var label: String
    }

    /// Head-to-head: the latest result per done ticket and engine.
    public struct BenchRow: Codable, Equatable, Sendable {
        public var ticket: String
        public var title: String
        public var agent: AgentKind
        public var result: String
        public var minutes: Double?
        public var costUsd: Double?
        public var tokens: Int?
        public var why: String?
    }

    public var windows: [Int]
    public var all: Scope?
    public var byRepo: [Scope]
    public var bench: [BenchRow]?

    public func scope(repo: String?) -> Scope? {
        guard let repo else { return all }
        return byRepo.first { $0.repo == repo }
    }

    public static func decode(_ data: Data) throws -> StatsSnapshot {
        try StatusCoding.decoder.decode(StatsSnapshot.self, from: data)
    }
}

public enum StatsFormat {
    /// 22 → "22 min", 190 → "3 h 10 m".
    public static func minutes(_ m: Double?) -> String {
        guard let m else { return "–" }
        if m < 60 { return m < 10 ? String(format: "%.1f min", m) : "\(Int(m.rounded())) min" }
        let total = Int(m.rounded())
        return "\(total / 60) h \(total % 60) m"
    }

    /// 41_200 → "41k tokens".
    public static func tokens(_ t: Int?) -> String {
        guard let t else { return "–" }
        if t >= 1_000_000 { return String(format: "%.1fM tokens", Double(t) / 1_000_000) }
        if t >= 1_000 { return "\(t / 1_000)k tokens" }
        return "\(t) tokens"
    }

    public static func dollars(_ d: Double?) -> String {
        guard let d else { return "–" }
        return String(format: "$%.2f", d)
    }
}
