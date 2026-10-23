import XCTest
@testable import RunwayCore

final class StatusDecodingTests: XCTestCase {
    private func sample() throws -> Status {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "sample-status", withExtension: "json",
                                                  subdirectory: "Fixtures"))
        return try Status.decode(Data(contentsOf: url))
    }

    func testReposMatchTheMock() throws {
        let status = try sample()
        XCTAssertEqual(status.repos.map(\.name), ["recipe-app", "my-website", "invoice-tool"])
        XCTAssertEqual(status.repos.map(\.state), [.running, .idle, .paused])
        XCTAssertEqual(status.repos.map(\.mainComputer), ["This Mac", "Mac mini", "Work Mac"])
        XCTAssertEqual(status.repo(named: "invoice-tool")?.runsOn, .main)
    }

    func testRunnersAndLoad() throws {
        let status = try sample()
        XCTAssertEqual(status.runners.map(\.name), ["This Mac", "Mac mini", "Work Mac", "Cloud"])
        XCTAssertEqual(status.runners.map(\.kind), [.thisMac, .sshMac, .sshMac, .cloud])
        XCTAssertEqual(status.runners.map(\.load), ["1 of 2", "1 of 2", "asleep", "1 of 3"])
    }

    func testAgents() throws {
        let status = try sample()
        let claude = try XCTUnwrap(status.agent(.claude))
        XCTAssertFalse(claude.available)
        let parts = Calendar.current.dateComponents([.hour, .minute], from: try XCTUnwrap(claude.restingUntil))
        XCTAssertEqual(parts.hour, 19)
        XCTAssertEqual(parts.minute, 30)
        XCTAssertEqual(status.agent(.codex)?.available, true)
    }

    func testTicketsByColumn() throws {
        let status = try sample()
        XCTAssertEqual(status.tickets.map(\.id).sorted(), (11...21).map { "T-\($0)" })
        let ids = { (column: Ticket.Column) in status.tickets(repo: "recipe-app", in: column).map(\.id) }
        XCTAssertEqual(ids(.needsYou), ["T-14", "T-17"])
        XCTAssertEqual(ids(.upNext), ["T-18", "T-19", "T-20"])
        XCTAssertEqual(ids(.running), ["T-15", "T-16", "T-21"])
        XCTAssertEqual(ids(.done), ["T-11", "T-12", "T-13"])
        XCTAssertEqual(status.needsYou.count, 2)
    }

    func testTicketDetails() throws {
        let status = try sample()
        let byID = Dictionary(uniqueKeysWithValues: status.tickets.map { ($0.id, $0) })
        let t14 = try XCTUnwrap(byID["T-14"])
        XCTAssertEqual(t14.risk, .notLow)
        XCTAssertEqual(t14.agent, .claude)
        XCTAssertEqual(t14.question?.goLabel, "Merge")
        XCTAssertEqual(t14.question?.noLabel, "Not yet")
        let t19 = try XCTUnwrap(byID["T-19"])
        XCTAssertTrue(t19.pinned)
        XCTAssertEqual(t19.placeLine, "Mac mini (pinned)")
        XCTAssertEqual(byID["T-18"]?.placeLine, "next free runner")
        XCTAssertEqual(byID["T-20"]?.waitsOn, ["T-18"])
        XCTAssertEqual(byID["T-15"]?.stage, .review)
        XCTAssertEqual(byID["T-16"]?.stage, .build)
        XCTAssertEqual(byID["T-21"]?.runsOn, "Cloud")
        XCTAssertNil(byID["T-18"]?.stage)
    }

    func testActivityAndSetup() throws {
        let status = try sample()
        XCTAssertEqual(status.activity.count, 14)
        XCTAssertEqual(status.activity.first?.kind, .filed)
        XCTAssertTrue(status.activity.contains { $0.kind == .limit && $0.repo == nil })
        XCTAssertEqual(status.setup.map(\.runner), ["This Mac", "Mac mini", "Cloud"])
        XCTAssertEqual(status.setup[2].codex, .signIn)
    }

    func testRoundTrip() throws {
        let status = try sample()
        XCTAssertEqual(try Status.decode(status.encoded()), status)
    }

    func testRejectsUnknownColumn() {
        let bad = #"{"version":1,"generated_at":"2026-10-23T19:16:00Z","repos":[],"runners":[],"agents":[],"#
            + #""tickets":[{"id":"T-1","repo":"r","title":"t","column":"limbo","agent":"any","risk":"low","#
            + #""pinned":false,"filed_from":"x","filed_at":"2026-10-23T19:16:00Z","waits_on":[]}],"#
            + #""activity":[],"setup":[]}"#
        XCTAssertThrowsError(try Status.decode(Data(bad.utf8)))
    }
}
