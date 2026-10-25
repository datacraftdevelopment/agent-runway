import Foundation

/// The `runway` command, which holds every rule. The app runs it through the person's login shell, so tmux, claude,
/// codex and gh resolve exactly as they do in Terminal (an app launched from Finder gets a bare PATH).
struct RunwayCLI: Sendable {
    let path: String

    /// `RUNWAY_CLI`, else the copy inside Runway.app, else `bin/runway` of the checkout the app was built from.
    static func find() -> RunwayCLI? {
        let fm = FileManager.default
        if let env = ProcessInfo.processInfo.environment["RUNWAY_CLI"], fm.isExecutableFile(atPath: env) {
            return RunwayCLI(path: env)
        }
        if let bundled = Bundle.main.resourceURL?.appendingPathComponent("cli/bin/runway"),
           fm.isExecutableFile(atPath: bundled.path) {
            return RunwayCLI(path: bundled.path)
        }
        var dir = Bundle.main.executableURL?.deletingLastPathComponent()
        while let current = dir, current.path != "/" {
            let candidate = current.appendingPathComponent("bin/runway")
            if fm.isExecutableFile(atPath: candidate.path), fm.fileExists(atPath: current.appendingPathComponent("runway/cli.py").path) {
                return RunwayCLI(path: candidate.path)
            }
            dir = current.deletingLastPathComponent()
        }
        return nil
    }

    struct Result: Sendable {
        let status: Int32
        let output: String
        let error: String
    }

    /// The shell line for `runway <args>`, each argument quoted.
    func line(_ args: [String]) -> String {
        ([path] + args).map(Self.quote).joined(separator: " ")
    }

    static func quote(_ s: String) -> String { "'" + s.replacingOccurrences(of: "'", with: "'\\''") + "'" }

    /// Runs `runway <args>` to completion off the main thread.
    func run(_ args: [String]) async -> Result {
        let process = loginShell(line(args))
        return await withCheckedContinuation { continuation in
            let out = Pipe(), err = Pipe()
            process.standardOutput = out
            process.standardError = err
            process.terminationHandler = { p in
                let o = String(decoding: out.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
                let e = String(decoding: err.fileHandleForReading.readDataToEndOfFile(), as: UTF8.self)
                continuation.resume(returning: Result(status: p.terminationStatus, output: o, error: e))
            }
            do { try process.run() } catch {
                continuation.resume(returning: Result(status: -1, output: "", error: error.localizedDescription))
            }
        }
    }

    /// `runway loop` as a child of the app: it stops when the app goes (`--parent-pid`), and the app stops it on quit.
    func startLoop(log: URL) -> Process? {
        let pid = ProcessInfo.processInfo.processIdentifier
        let process = loginShell("exec " + line(["loop", "--parent-pid", String(pid)]))
        FileManager.default.createFile(atPath: log.path, contents: nil)
        if let handle = try? FileHandle(forWritingTo: log) {
            handle.seekToEndOfFile()
            process.standardOutput = handle
            process.standardError = handle
        }
        do { try process.run() } catch { return nil }
        return process
    }

    private func loginShell(_ line: String) -> Process {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: ProcessInfo.processInfo.environment["SHELL"] ?? "/bin/zsh")
        process.arguments = ["-lc", line]
        return process
    }
}
