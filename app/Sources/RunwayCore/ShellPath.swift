import Foundation

/// PATH as the person's Terminal has it. An app opened from Finder gets a bare PATH, and `zsh -l` without `-i` skips
/// ~/.zshrc, which is where Claude Code's installer and most npm setups add their folders. So this asks an interactive
/// login shell once, falling back to a login shell. The shell writes PATH to a file, so whatever ~/.zshrc prints or
/// leaves running can't get in the way, and it gets no stdin, so it can't wait for input.
public enum ShellPath {
    public static func resolve(shell: String, environment: [String: String]? = nil,
                               timeout: TimeInterval = 10) -> String? {
        let fm = FileManager.default
        let file = fm.temporaryDirectory.appendingPathComponent("runway-path-\(UUID().uuidString)")
        defer { try? fm.removeItem(at: file) }
        for flags in ["-lic", "-lc"] {
            let process = Process()
            process.executableURL = URL(fileURLWithPath: shell)
            process.arguments = [flags, "printf %s \"$PATH\" > \"$1\"", "runway", file.path]
            if let environment { process.environment = environment }
            process.standardInput = FileHandle.nullDevice
            process.standardOutput = FileHandle.nullDevice
            process.standardError = FileHandle.nullDevice
            let done = DispatchSemaphore(value: 0)
            process.terminationHandler = { _ in done.signal() }
            do { try process.run() } catch { continue }
            if done.wait(timeout: .now() + timeout) == .timedOut {
                process.terminate()
                continue
            }
            if let path = try? String(contentsOf: file, encoding: .utf8)
                .trimmingCharacters(in: .whitespacesAndNewlines), !path.isEmpty {
                return path
            }
        }
        return nil
    }
}
