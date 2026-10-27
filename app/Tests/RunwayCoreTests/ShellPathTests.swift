import XCTest
@testable import RunwayCore

/// #42: an app opened from Finder, engines on a folder that only ~/.zshrc adds to PATH.
final class ShellPathTests: XCTestCase {
    private func home(zshrc: String) throws -> URL {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("shellpath-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try "".write(to: dir.appendingPathComponent(".zprofile"), atomically: true, encoding: .utf8)
        try zshrc.write(to: dir.appendingPathComponent(".zshrc"), atomically: true, encoding: .utf8)
        addTeardownBlock { try? FileManager.default.removeItem(at: dir) }
        return dir
    }

    private func env(_ home: URL) -> [String: String] {
        ["HOME": home.path, "USER": NSUserName(), "SHELL": "/bin/zsh", "PATH": "/usr/bin:/bin:/usr/sbin:/sbin"]
    }

    func testFindsAFolderOnlyZshrcAdds() throws {
        let h = try home(zshrc: "echo welcome back\nexport PATH=\"$HOME/.local/bin:$PATH\"\n")
        let path = try XCTUnwrap(ShellPath.resolve(shell: "/bin/zsh", environment: env(h)))
        XCTAssertTrue(path.split(separator: ":").contains(Substring(h.path + "/.local/bin")), path)
    }

    func testAZshrcWaitingForInputDoesNotHang() throws {
        let h = try home(zshrc: "read answer\nexport PATH=\"$HOME/tools:$PATH\"\n")
        let start = Date()
        let path = try XCTUnwrap(ShellPath.resolve(shell: "/bin/zsh", environment: env(h), timeout: 5))
        XCTAssertLessThan(Date().timeIntervalSince(start), 5)
        XCTAssertTrue(path.contains(h.path + "/tools"), path)
    }

    func testDecodesInstallAndNote() throws {
        let json = #"{"name": "tmux", "ok": false, "path": null, "why": "w", "fix": "brew install tmux", "install": "tmux"}"#
        let tool = try StatusCoding.decoder.decode(SetupReport.Tool.self, from: Data(json.utf8))
        XCTAssertEqual(tool.install, "tmux")
        XCTAssertNil(tool.note)
    }
}
