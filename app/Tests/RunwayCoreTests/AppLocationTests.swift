import XCTest
@testable import RunwayCore

final class AppLocationTests: XCTestCase {
    let home = "/Users/someone"

    func testApplicationsFoldersAreInstalled() {
        XCTAssertEqual(AppLocation.classify(bundlePath: "/Applications/Runway.app", home: home), .installed)
        XCTAssertEqual(AppLocation.classify(bundlePath: "/Users/someone/Applications/Runway.app", home: home), .installed)
    }

    func testDownloadsDesktopAndDiskImagesAreElsewhere() {
        XCTAssertEqual(AppLocation.classify(bundlePath: "/Users/someone/Downloads/Runway.app", home: home), .elsewhere)
        XCTAssertEqual(AppLocation.classify(bundlePath: "/Volumes/Agent Runway/Runway.app", home: home), .elsewhere)
        let translocated = "/private/var/folders/xy/abc/T/AppTranslocation/1234-5678/d/Runway.app"
        XCTAssertEqual(AppLocation.classify(bundlePath: translocated, home: home), .elsewhere)
    }

    func testDeveloperBuildsAreNeverAsked() {
        XCTAssertEqual(AppLocation.classify(bundlePath: "/src/agent-runway/app/build/Runway.app", home: home), .development)
        XCTAssertEqual(AppLocation.classify(bundlePath: "/src/agent-runway/app/.build/release/Runway", home: home), .development)
        XCTAssertEqual(AppLocation.classify(
            bundlePath: "/Users/someone/Library/Developer/Xcode/DerivedData/R/Build/Products/Release/Runway.app",
            home: home), .development)
    }

    func testASubfolderOfApplicationsIsElsewhere() {
        XCTAssertEqual(AppLocation.classify(bundlePath: "/Applications/Tools/Runway.app", home: home), .elsewhere)
    }
}
