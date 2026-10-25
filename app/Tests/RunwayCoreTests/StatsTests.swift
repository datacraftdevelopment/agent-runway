import XCTest
@testable import RunwayCore

final class StatsTests: XCTestCase {
    /// The fixture is `runway stats --json` on a copy of the practice repo's three tickets.
    func testDecodesThePracticeStats() throws {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "stats", withExtension: "json", subdirectory: "Fixtures"))
        let stats = try StatsSnapshot.decode(Data(contentsOf: url))
        XCTAssertEqual(stats.windows, [7, 30])
        let week = try XCTUnwrap(stats.scope(repo: nil)?.window(7))
        XCTAssertEqual(week.merged, 2)
        XCTAssertEqual(week.handsOff, 1)
        XCTAssertEqual(week.handsOffTickets, ["T-1"])
        XCTAssertEqual(week.otherTickets, ["T-3"])
        let codex = try XCTUnwrap(week.costPerTicket.byAgent.first { $0.agent == .codex })
        XCTAssertNil(codex.medianUsd)
        XCTAssertNotNil(codex.medianTokens)
        XCTAssertEqual(stats.scope(repo: "runway-practice")?.waiting.map(\.id), ["T-2"])
        XCTAssertEqual(stats.scope(repo: "runway-practice")?.waiting.first?.label, "not low risk")
    }

    func testFormats() {
        XCTAssertEqual(StatsFormat.minutes(22), "22 min")
        XCTAssertEqual(StatsFormat.minutes(190), "3 h 10 m")
        XCTAssertEqual(StatsFormat.minutes(1.3), "1.3 min")
        XCTAssertEqual(StatsFormat.tokens(41_200), "41k tokens")
        XCTAssertEqual(StatsFormat.dollars(0.8841), "$0.88")
        XCTAssertEqual(StatsFormat.minutes(nil), "–")
    }
}
