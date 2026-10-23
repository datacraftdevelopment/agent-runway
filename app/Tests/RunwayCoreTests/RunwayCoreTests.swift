import XCTest
@testable import RunwayCore

final class RunwayCoreTests: XCTestCase {
    func testVersion() { XCTAssertFalse(RunwayCore.version.isEmpty) }
}
