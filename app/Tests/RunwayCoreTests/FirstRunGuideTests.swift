import XCTest
@testable import RunwayCore

final class SetupGuideTests: XCTestCase {
    /// The doctor fixture (Claude Code ready, Codex missing, GitHub signed out, skills only in Claude Code, no repo),
    /// adjusted per test.
    private func report(_ change: (inout SetupReport) -> Void = { _ in }) throws -> SetupReport {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "doctor", withExtension: "json", subdirectory: "Fixtures"))
        var r = try SetupReport.decode(Data(contentsOf: url))
        change(&r)
        return r
    }

    private func allSet(_ r: inout SetupReport) {
        r.ready = true
        r.databaseExists = true
        r.skills.installed = true
        r.repos = ["app"]
    }

    func testNeededUntilEverythingIsThere() throws {
        XCTAssertFalse(SetupGuide.needed(try report(allSet)))
        XCTAssertTrue(SetupGuide.needed(try report { allSet(&$0); $0.ready = false }))
        XCTAssertTrue(SetupGuide.needed(try report { allSet(&$0); $0.databaseExists = false }))
        XCTAssertTrue(SetupGuide.needed(try report { allSet(&$0); $0.skills.installed = false }))
        XCTAssertTrue(SetupGuide.needed(try report { allSet(&$0); $0.repos = [] }))
        // The Terminal link is optional: missing it alone never brings the walkthrough back.
        XCTAssertFalse(SetupGuide.needed(try report { allSet(&$0); $0.command.linked = false }))
        // A runway too old to say whether the database exists isn't taken as missing.
        XCTAssertFalse(SetupGuide.needed(try report { allSet(&$0); $0.databaseExists = nil }))
    }

    func testStartsAtTheFirstThingMissing() throws {
        XCTAssertEqual(SetupGuide.start(nil, firstLaunch: true), .welcome)
        XCTAssertEqual(SetupGuide.start(try report(allSet), firstLaunch: true), .welcome)
        XCTAssertEqual(SetupGuide.start(nil, firstLaunch: false), .check)
        XCTAssertEqual(SetupGuide.start(try report { allSet(&$0); $0.ready = false }, firstLaunch: false), .check)
        XCTAssertEqual(SetupGuide.start(try report { allSet(&$0); $0.skills.installed = false }, firstLaunch: false),
                       .install)
        XCTAssertEqual(SetupGuide.start(try report { allSet(&$0); $0.databaseExists = false }, firstLaunch: false),
                       .install)
        XCTAssertEqual(SetupGuide.start(try report { allSet(&$0); $0.repos = [] }, firstLaunch: false), .next)
    }

    func testItemsSayWhatIsThereAndWhatGetsSkipped() throws {
        let fresh = SetupGuide.items(try report { $0.databaseExists = false; $0.skills.installed = false })
        XCTAssertEqual(fresh.map(\.kind), [.database, .command, .skills])
        XCTAssertEqual(fresh.map(\.done), [false, false, false])
        XCTAssertEqual(fresh.last?.title, "The Agent Runway skills in Claude Code")
        XCTAssertFalse(fresh.last?.skipped ?? true)
        // Installed but signed out still gets the skills: the plugin commands need no sign-in.
        let signedOut = SetupGuide.items(try report { $0.engines = []; $0.skills.installed = false })
        XCTAssertFalse(signedOut.last?.skipped ?? true)
        let noEngine = SetupGuide.items(try report {
            $0.skills.installed = false
            for i in $0.tools.indices where ["claude", "codex"].contains($0.tools[i].name) { $0.tools[i].ok = false }
        })
        XCTAssertTrue(noEngine.last?.skipped ?? false)
        XCTAssertEqual(noEngine.last?.title, "The Agent Runway skills in Claude Code or Codex")
        let both = SetupGuide.items(try report {
            for i in $0.tools.indices { $0.tools[i].ok = true }
            $0.skills.installed = true
        })
        XCTAssertEqual(both.last?.title, "The Agent Runway skills in Claude Code and Codex")
        XCTAssertTrue(both.last?.done ?? false)
        XCTAssertTrue(both.first?.done ?? false)        // an older runway (no database_exists) counts it as there
        let offPath = SetupGuide.items(try report { $0.command.linked = true; $0.command.linkDirOnPath = false })
        XCTAssertTrue(offPath[1].done)
        XCTAssertTrue(offPath[1].detail.contains("isn't on your PATH"))
    }

    func testOutdatedSkillsShowAsAnUpdateWithoutReopeningTheWalkthrough() throws {
        var r = try report(allSet)
        r.skills.version = "0.2.1"
        r.skills.claudeVersion = "0.2.0"
        r.skills.outdated = true
        // Not a reason to reopen the walkthrough on launch (What's New offers it); opened by hand, it starts there.
        XCTAssertFalse(SetupGuide.needed(r))
        XCTAssertEqual(SetupGuide.start(r, firstLaunch: false), .install)
        let skills = try XCTUnwrap(SetupGuide.items(r).last)
        XCTAssertEqual(skills.title, "Update the Agent Runway skills in Claude Code")
        XCTAssertFalse(skills.done)
        XCTAssertTrue(skills.detail.contains("Yours are 0.2.0; this Runway carries 0.2.1"))
        r.skills.codexVersion = "0.1.0"
        XCTAssertEqual(SetupGuide.installedVersions(r), "0.2.0 in Claude Code and 0.1.0 in Codex")
        r.skills.outdated = false
        XCTAssertTrue(try XCTUnwrap(SetupGuide.items(r).last).done)
    }

    func testFirstPromptNamesTheRepoAndTheSkill() {
        XCTAssertTrue(SetupGuide.firstPrompt(repo: "app").contains("work on app:"))
        XCTAssertTrue(SetupGuide.firstPrompt(repo: nil).contains("file-tickets skill"))
    }
}

final class ReleaseNotesTests: XCTestCase {
    func testVersionsCompareNumberByNumber() {
        let v = { (s: String) in AppVersion(s)! }
        XCTAssertLessThan(v("0.9.0"), v("0.10.0"))
        XCTAssertLessThan(v("0.1.0"), v("0.1.1"))
        XCTAssertEqual(v("1.0"), v("1.0.0"))
        XCTAssertLessThan(v("1.2"), v("1.2.1"))
        XCTAssertEqual(v("0.2.0-beta"), v("0.2.0"))
        XCTAssertNil(AppVersion("dev"))
        XCTAssertNil(AppVersion("1..2"))
        XCTAssertEqual(v(" 2.0.1 ").description, "2.0.1")
    }

    func testParsesFrontMatterLinesAndSections() throws {
        let text = "---\nbig: true\n---\n- One engine is enough.\n- Two reviews.\n\n### Hands off\n- Stats.\n- Retros.\n"
        let note = try XCTUnwrap(ReleaseNote(version: "0.2.0", text: text))
        XCTAssertTrue(note.big)
        XCTAssertEqual(note.lines, ["One engine is enough.", "Two reviews."])
        XCTAssertEqual(note.sections, [.init(title: "Hands off", lines: ["Stats.", "Retros."])])
        let small = try XCTUnwrap(ReleaseNote(version: "0.1.1", text: "- A fix.\n"))
        XCTAssertFalse(small.big)
        XCTAssertEqual(small.lines, ["A fix."])
        XCTAssertNil(ReleaseNote(version: "README", text: ""))
    }

    private func notes(_ versions: String...) -> [ReleaseNote] {
        versions.map { ReleaseNote(version: $0, text: "- \($0)")! }
    }

    func testWhichNotesToShow() {
        let all = notes("0.1.0", "0.1.1", "0.2.0", "0.3.0")
        let shown = { (d: WhatsNew.Decision) in d.notes.map(\.version.description) }
        // Every version since the last one seen, up to this one, newest first.
        var d = WhatsNew.decide(current: "0.2.0", lastSeen: "0.1.0", firstLaunch: false, notes: all)
        XCTAssertEqual(shown(d), ["0.2.0", "0.1.1"])
        XCTAssertTrue(d.remember)
        // Already seen: nothing, and nothing to store.
        d = WhatsNew.decide(current: "0.2.0", lastSeen: "0.2.0", firstLaunch: false, notes: all)
        XCTAssertEqual(shown(d), []); XCTAssertFalse(d.remember)
        // A downgrade never shows notes or lowers what was seen.
        d = WhatsNew.decide(current: "0.1.1", lastSeen: "0.3.0", firstLaunch: false, notes: all)
        XCTAssertEqual(shown(d), []); XCTAssertFalse(d.remember)
        // First launch ever: the walkthrough instead, and this version counts as seen.
        d = WhatsNew.decide(current: "0.2.0", lastSeen: nil, firstLaunch: true, notes: all)
        XCTAssertEqual(shown(d), []); XCTAssertTrue(d.remember)
        // Upgraded from a version before What's New: this version's notes only.
        d = WhatsNew.decide(current: "0.1.1", lastSeen: nil, firstLaunch: false, notes: all)
        XCTAssertEqual(shown(d), ["0.1.1"])
        // A version with no notes file still counts as seen.
        d = WhatsNew.decide(current: "0.2.1", lastSeen: "0.2.0", firstLaunch: false, notes: all)
        XCTAssertEqual(shown(d), []); XCTAssertTrue(d.remember)
        // A build with no proper version shows nothing and stores nothing.
        d = WhatsNew.decide(current: "dev", lastSeen: "0.1.0", firstLaunch: false, notes: all)
        XCTAssertEqual(shown(d), []); XCTAssertFalse(d.remember)
        XCTAssertEqual(WhatsNew.all(current: "0.2.0", notes: all).map(\.version.description), ["0.2.0", "0.1.1", "0.1.0"])
    }

    func testTheRepoNotesParse() throws {
        // app/release-notes, as make-app.sh copies it into the app.
        let folder = URL(fileURLWithPath: #filePath).deletingLastPathComponent().deletingLastPathComponent()
            .deletingLastPathComponent().appendingPathComponent("release-notes")
        let notes = ReleaseNote.load(from: folder)
        XCTAssertFalse(notes.isEmpty)
        for note in notes { XCTAssertFalse(note.lines.isEmpty && note.sections.isEmpty, "\(note.version) is empty") }
        XCTAssertEqual(notes.map(\.version), notes.map(\.version).sorted(by: >))
    }
}
