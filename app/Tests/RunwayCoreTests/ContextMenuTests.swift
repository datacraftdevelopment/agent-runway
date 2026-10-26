import XCTest
@testable import RunwayCore

final class ContextMenuTests: XCTestCase {
    private func status() throws -> Status {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "sample-status", withExtension: "json",
                                                  subdirectory: "Fixtures"))
        return try Status.decode(Data(contentsOf: url))
    }

    private func titles(_ items: [MenuItem]) -> [String] {
        items.map { $0.isDivider ? "—" : $0.title }
    }

    private func actions(_ items: [MenuItem]) -> [MenuAction] { items.compactMap(\.action) }

    func testDecodesTheNewFields() throws {
        let s = try status()
        XCTAssertEqual(s.archived, [ArchivedRepo(name: "old-site", tickets: 4)])
        XCTAssertEqual(s.repos.first?.slug, "someone/recipe-app")
        XCTAssertNotNil(s.repos.first?.path)
        XCTAssertNil(s.runners.first?.pausedUntil)
    }

    func testTicketMenuFollowsItsState() throws {
        let s = try status()
        let needs = try XCTUnwrap(s.tickets.first { $0.column == .needsYou && $0.taken != true && $0.question != nil })
        let menu = ContextMenus.ticket(needs, runners: s.runners)
        XCTAssertEqual(menu.first?.action, .discussTicket)
        XCTAssertTrue(actions(menu).contains(.go))
        XCTAssertTrue(actions(menu).contains(.no))
        XCTAssertTrue(actions(menu).contains(.takeBack))
        XCTAssertFalse(actions(menu).contains(.giveBack))
        XCTAssertEqual(menu.last?.action, .deleteTicket)
        XCTAssertTrue(menu.last?.destructive ?? false)
        let runsOn = try XCTUnwrap(menu.first { $0.title == "Runs on" })
        XCTAssertEqual(runsOn.children.count, s.runners.count + 1)
        XCTAssertEqual(runsOn.children.filter(\.checked).count, 1)

        // Running: no delete, no Go/No, no Runs on.
        let running = try XCTUnwrap(s.tickets.first { $0.column == .running })
        let r = actions(ContextMenus.ticket(running, runners: s.runners))
        XCTAssertFalse(r.contains(.deleteTicket))
        XCTAssertFalse(r.contains(.go))
        XCTAssertNil(ContextMenus.ticket(running, runners: s.runners).first { $0.title == "Runs on" })

        // Done: chat, PR, id, delete; nothing to take back.
        var done = try XCTUnwrap(s.tickets.first { $0.column == .done })
        done.prUrl = "https://github.com/someone/recipe-app/pull/1"
        let d = actions(ContextMenus.ticket(done, runners: s.runners))
        XCTAssertEqual(d, [.discussTicket, .openPR, .copyTicketID, .deleteTicket])

        // Taken back: copy the prompt again and give back.
        var taken = needs
        taken.taken = true
        let t = actions(ContextMenus.ticket(taken, runners: s.runners))
        XCTAssertTrue(t.contains(.copyTakePrompt) && t.contains(.giveBack))
        XCTAssertFalse(t.contains(.takeBack) || t.contains(.go))
    }

    func testRepoMenuFollowsItsState() throws {
        let s = try status()
        let paused = try XCTUnwrap(s.repos.first { $0.state == .paused })
        let menu = ContextMenus.repo(paused, runners: s.runners, hasDone: true)
        XCTAssertEqual(menu.first?.action, .discussRepo)
        XCTAssertTrue(actions(menu).contains(.resumeRepo))
        XCTAssertFalse(actions(menu).contains(.pauseRepo))
        XCTAssertEqual(Array(actions(menu).suffix(3)), [.clearDone, .archive, .removeRepo])
        let main = try XCTUnwrap(menu.first { $0.title == "Main computer" })
        XCTAssertFalse(main.children.contains { $0.title == "Cloud" })      // a clone doesn't live in the cloud
        XCTAssertEqual(main.children.first { $0.checked }?.title, paused.mainComputer)
        let runsOn = try XCTUnwrap(menu.first { $0.title == "Runs on" })
        XCTAssertEqual(runsOn.children.first { $0.checked }?.action, .repoRunsOn(.main))

        var bare = try XCTUnwrap(s.repos.first { $0.state != .paused })
        bare.slug = nil
        bare.path = nil
        let b = actions(ContextMenus.repo(bare, runners: s.runners, hasDone: false))
        XCTAssertTrue(b.contains(.pauseRepo))
        XCTAssertFalse(b.contains(.openGitHub) || b.contains(.revealFolder) || b.contains(.clearDone))
        // Never two dividers in a row, or one at either end, whatever is left out.
        for items in [ContextMenus.repo(bare, runners: s.runners, hasDone: false), menu]
            + s.tickets.map({ ContextMenus.ticket($0, runners: s.runners) }) {
            let marks = titles(items)
            XCTAssertNotEqual(marks.first, "—")
            XCTAssertNotEqual(marks.last, "—")
            XCTAssertFalse(zip(marks, marks.dropFirst()).contains { $0 == "—" && $1 == "—" }, "\(marks)")
        }
    }

    func testRunnerLoadLineAndMaxSessions() throws {
        var mac = try status().runners[0]
        XCTAssertEqual(mac.loadLine, "1 of 2 · memory ok")
        mac.load?.hold = "busy (memory)"
        XCTAssertEqual(mac.loadLine, "holding: busy (memory)")
        mac.load = nil                                                   // an older runway sends no reading
        XCTAssertEqual(mac.loadLine, "1 of 2")
        let max = try XCTUnwrap(ContextMenus.runner(mac).first { $0.title == "Max sessions" })
        XCTAssertEqual(max.children.count, 8)
        XCTAssertEqual(max.children.first { $0.checked }?.action, .maxSessions(mac.slotsTotal))
    }

    func testDecodesBlockersAndHolds() throws {
        let json = #"{"id":"T-9","repo":"r","title":"t","column":"up_next","agent":"any","risk":"low","pinned":false,"#
            + #""filed_from":"x","filed_at":"2026-10-26T10:00:00Z","waits_on":["T-4"],"#
            + #""blocked_by":[{"id":"T-4","title":"First","column":"running","waits_on":[]}],"#
            + #""blocks":["T-12"],"hold":"waiting: This Mac is busy (memory)"}"#
        let t = try StatusCoding.decoder.decode(Ticket.self, from: Data(json.utf8))
        XCTAssertEqual(t.blockedBy?.first?.column, .running)
        XCTAssertEqual(t.blocks, ["T-12"])
        XCTAssertEqual(t.hold, "waiting: This Mac is busy (memory)")
        XCTAssertTrue(t.heldForCapacity)
        var overlap = t
        overlap.hold = "waiting: touches the same files as T-3"
        XCTAssertFalse(overlap.heldForCapacity)                         // Start anyway is for a busy Mac only
    }

    func testIdleReasonDecodesAndShortens() throws {
        let json = #"{"name":"handstand-log","state":"needs_you","status_line":"1 needs you","main_computer":"This Mac","#
            + #""runs_on":"main","idle_reason":"Nothing can run: 4 tickets wait on T-4, which needs you","idle_ticket":"T-4"}"#
        let repo = try StatusCoding.decoder.decode(Repo.self, from: Data(json.utf8))
        XCTAssertEqual(repo.idleTicket, "T-4")
        XCTAssertEqual(repo.idleShort, "4 tickets wait on T-4, which needs you")
        XCTAssertEqual(try status().loopRunning, true)
        XCTAssertNil(try status().repos[0].idleReason)
    }

    func testCheckCommandMenuAndSuggestion() throws {
        var repo = try status().repos[0]
        XCTAssertEqual(repo.checkCmd, "npm test")
        XCTAssertTrue(ContextMenus.repo(repo, runners: [], hasDone: false).contains { $0.title == "Check command…" })
        repo.checkCmd = nil
        XCTAssertTrue(ContextMenus.repo(repo, runners: [], hasDone: false).contains { $0.action == .setCheck
            && $0.title == "Set check command…" })
        let s = try RepoSuggestion.decode(Data(#"{"path":"/x","name":"x","git":true,"slug":"a/x","check":"swift test --package-path Core","commands":["swift build --package-path Core"]}"#.utf8))
        XCTAssertEqual(s.commands, ["swift build --package-path Core"])
    }

    func testTimerLinesPerColumn() throws {
        let now = Date(timeIntervalSince1970: 1_800_000_000)
        func ticket(_ column: String, _ timing: String) throws -> Ticket {
            let json = #"{"id":"T-1","repo":"r","title":"t","column":"\#(column)","agent":"any","risk":"low","pinned":false,"#
                + #""filed_from":"x","filed_at":"2026-10-26T10:00:00Z","waits_on":[],"timing":\#(timing)}"#
            return try StatusCoding.decoder.decode(Ticket.self, from: Data(json.utf8))
        }
        let iso = { (s: Double) in ISO8601DateFormatter().string(from: now.addingTimeInterval(-s)) }
        let running = try ticket("running", #"{"started_at":"\#(iso(2280))","stage":"build","stage_started_at":"\#(iso(720))"}"#)
        XCTAssertEqual(running.timerLine(now: now), "Build · 12 min · 38 min in all")
        XCTAssertEqual(try ticket("up_next", #"{"waiting_since":"\#(iso(3600))"}"#).timerLine(now: now), "Waiting 1 h")
        XCTAssertEqual(try ticket("needs_you", #"{"waiting_since":"\#(iso(1200))"}"#).timerLine(now: now),
                       "Waiting for you 20 min")
        XCTAssertEqual(try ticket("done", #"{"total_seconds":4320,"parts":{"build":600}}"#).timerLine(now: now),
                       "Took 1 h 12 min")
        XCTAssertEqual(Duration.words(97200), "1 d 3 h")
    }

    func testHandsOnTicketsAreYoursNotBlocked() throws {
        let s = try status()
        var t = try XCTUnwrap(s.tickets.first { $0.column == .upNext })
        t.handsOn = true
        XCTAssertTrue(t.yoursToDo)
        let menu = ContextMenus.ticket(t, runners: s.runners)
        XCTAssertTrue(menu.contains { $0.action == .markDone })
        XCTAssertTrue(menu.contains { $0.action == .copyTakePrompt })
        XCTAssertFalse(menu.contains { $0.action == .takeBack })            // already yours: nothing to take back
        XCTAssertNil(menu.first { $0.title == "Runs on" })                   // Runway never runs it
        var done = t
        done.column = .done
        done.doneLocally = true
        XCTAssertFalse(done.yoursToDo)
        let json = #"{"id":"T-9","repo":"r","title":"t","column":"up_next","agent":"any","risk":"low","pinned":false,"#
            + #""filed_from":"x","filed_at":"2026-10-26T10:00:00Z","waits_on":["T-3"],"hands_on":false,"#
            + #""blocked_by":[{"id":"T-3","title":"On the phone","column":"up_next","waits_on":[],"hands_on":true}]}"#
        let blocked = try StatusCoding.decoder.decode(Ticket.self, from: Data(json.utf8))
        XCTAssertEqual(blocked.blockedBy?.first?.handsOn, true)
        XCTAssertFalse(blocked.yoursToDo)
    }

    func testArchivedAndRunnerMenus() throws {
        let s = try status()
        XCTAssertEqual(actions(ContextMenus.archived(ArchivedRepo(name: "x", tickets: 1))), [.unarchive, .removeRepo])
        var runner = s.runners[0]
        XCTAssertEqual(actions(ContextMenus.runner(runner)), [.pauseRunner])
        runner.pausedUntil = Date()
        XCTAssertEqual(actions(ContextMenus.runner(runner)), [.resumeRunner])
    }
}
