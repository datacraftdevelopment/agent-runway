import XCTest
@testable import RunwayCore

final class SetupReportTests: XCTestCase {
    func testDecodesDoctorJSON() throws {
        let url = try XCTUnwrap(Bundle.module.url(forResource: "doctor", withExtension: "json", subdirectory: "Fixtures"))
        let report = try SetupReport.decode(Data(contentsOf: url))
        XCTAssertFalse(report.ready)
        XCTAssertFalse(report.command.linked)
        XCTAssertFalse(report.command.linkDirOnPath)
        XCTAssertEqual(report.tools.map(\.name), ["git", "gh", "tmux", "claude", "codex"])
        XCTAssertEqual(report.tools.first { !$0.ok }?.fix, "npm install -g @openai/codex")
        XCTAssertEqual(report.signins.filter { !$0.ok }.map(\.label), ["Codex", "GitHub"])
        XCTAssertTrue(report.skills.built)
        XCTAssertEqual(report.skills.claude, true)
        XCTAssertEqual(report.skills.codex, false)
        XCTAssertFalse(report.skills.installed)
        XCTAssertTrue(report.repos.isEmpty)
    }

    func testDecodesRepoSuggestion() throws {
        let json = #"{"path": "/tmp/app", "name": "app", "git": true, "slug": "someone/app", "check": "npm test"}"#
        let s = try RepoSuggestion.decode(Data(json.utf8))
        XCTAssertEqual(s.slug, "someone/app")
        XCTAssertEqual(s.check, "npm test")
        let bare = try RepoSuggestion.decode(Data(#"{"path": "/tmp/x", "name": "x", "git": false, "slug": null, "check": null}"#.utf8))
        XCTAssertNil(bare.check)
    }
}
