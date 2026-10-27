import Foundation

import RunwayCore

/// The `runway` command, which holds every rule. The app runs it through the person's login shell, with PATH as their
/// Terminal has it (an app launched from Finder gets a bare PATH, and a login shell alone skips ~/.zshrc), so tmux,
/// claude, codex, node and gh resolve exactly as they do in Terminal.
struct RunwayCLI: Sendable {
    let path: String

    /// The app's environment with the Terminal PATH, found once (ShellPath) and handed to every command, the loop too.
    /// RUNWAY_SHELL_PATH carries it to runway, which then doesn't ask the shell again and keeps that order. Opened
    /// from Terminal, the PATH the app has is that one.
    static let environment: [String: String] = {
        var env = ProcessInfo.processInfo.environment
        if isatty(STDIN_FILENO) == 0, let path = ShellPath.resolve(shell: env["SHELL"] ?? "/bin/zsh") {
            env["PATH"] = path
            env["RUNWAY_SHELL_PATH"] = path
        }
        return env
    }()

    /// Finds the Terminal PATH in the background at launch, so the first command doesn't wait for it.
    static func warmUp() {
        DispatchQueue.global(qos: .userInitiated).async { _ = environment }
    }

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
        process.environment = Self.environment
        return process
    }
}
