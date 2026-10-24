import XCTest
@testable import RunwayCore

final class UpdaterTests: XCTestCase {
    func testNoKeyTurnsUpdaterOff() {
        XCTAssertEqual(UpdaterState.decide(publicKey: nil), .off)
        XCTAssertEqual(UpdaterState.decide(publicKey: ""), .off)
        XCTAssertEqual(UpdaterState.decide(publicKey: "  \n"), .off)
    }

    func testKeyTurnsUpdaterOn() {
        XCTAssertEqual(UpdaterState.decide(publicKey: "abc123="), .on)
    }

    func testDisabledStaysOffEvenWithAKey() {
        XCTAssertEqual(UpdaterState.decide(publicKey: "abc123=", enabled: false), .off)
    }

    func testOffMenuSaysWhy() {
        XCTAssertEqual(UpdaterState.off.menuNote, "Updates off in this build")
        XCTAssertNil(UpdaterState.on.menuNote)
    }
}
