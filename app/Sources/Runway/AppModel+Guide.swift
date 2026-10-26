import AppKit
import Foundation
import RunwayCore

/// The first-run walkthrough and What's New: what to open at launch, "Set it up", and the release notes.
extension AppModel {
    enum LaunchScreen: Equatable { case guide, whatsNew, none }

    /// ~/.runway/runway.db (or under RUNWAY_HOME), the same place the runway command uses.
    static var databasePath: String {
        let env = ProcessInfo.processInfo.environment
        let home = env["RUNWAY_HOME"] ?? ((env["HOME"] ?? NSHomeDirectory()) + "/.runway")
        return home + "/runway.db"
    }

    /// `RUNWAY_DEFAULTS_SUITE` keeps a trial run (screenshots, a throwaway HOME) out of the real app's settings.
    private var defaults: UserDefaults {
        ProcessInfo.processInfo.environment["RUNWAY_DEFAULTS_SUITE"].flatMap(UserDefaults.init(suiteName:)) ?? .standard
    }

    private static let lastSeenKey = "whatsNewLastSeen"

    /// The running version; `RUNWAY_VERSION` stands in for it when trying What's New on a build.
    var appVersion: String { ProcessInfo.processInfo.environment["RUNWAY_VERSION"] ?? AppUpdater.shared.version }

    /// `runway doctor --json`, awaited. It only looks: nothing is created before "Set it up".
    @discardableResult
    func checkMac() async -> SetupReport? {
        guard let cli else { return nil }
        checking = true
        let result = await cli.run(["doctor", "--json"])
        checking = false
        guard let report = try? SetupReport.decode(Data(result.output.utf8)) else {
            setupMessage = "The check didn't finish: " + (result.error.isEmpty ? "no report" : result.error)
            return nil
        }
        setup = report
        setupMessage = nil
        return report
    }

    /// Run once per launch, after anything that has to come first (the move-to-Applications prompt). The first launch
    /// ever opens the walkthrough on its welcome; later launches check again and open it only if something is
    /// missing, else What's New when this version is newer than the last one the person saw.
    func launchScreen() async -> LaunchScreen {
        guard source == .live else { return .none }
        if firstLaunch {
            guideStep = .welcome
            Task { await checkMac() }
            rememberSeen()
            return .guide
        }
        if let report = await checkMac(), SetupGuide.needed(report) {
            guideStep = SetupGuide.start(report, firstLaunch: false)
            return .guide
        }
        await updateSkillsAfterUpdate()
        let decision = WhatsNew.decide(current: appVersion, lastSeen: defaults.string(forKey: Self.lastSeenKey),
                                       firstLaunch: false, notes: Self.releaseNotes())
        if decision.remember { rememberSeen() }
        whatsNew = decision.notes
        return decision.notes.isEmpty ? .none : .whatsNew
    }

    private func rememberSeen() {
        guard AppVersion(appVersion) != nil, RenderMode.folder == nil else { return }
        defaults.set(appVersion, forKey: Self.lastSeenKey)
    }

    /// After an app update brought newer skills: update the Agent Runway plugin in each engine that already has it,
    /// without asking (it's the install the person approved at setup; nothing is added to an engine without it).
    /// What's New then says what happened; if it didn't work, why, with "Update the skills" to try again.
    func updateSkillsAfterUpdate() async {
        guard let cli, setup?.skills.outdated == true else { return }
        updatingSkills = true
        let result = await cli.run(["install-skills", "--update-only"])
        updatingSkills = false
        let said = (result.status == 0 ? result.output : result.error).trimmingCharacters(in: .whitespacesAndNewlines)
        let after = await checkMac()
        if result.status == 0, after?.skills.outdated != true {
            let engines = [after?.skills.claudeVersion.map { _ in "Claude Code" },
                           after?.skills.codexVersion.map { _ in "Codex" }].compactMap { $0 }
            skillsNote = "Skills updated to \(after?.skills.version ?? "the new version") in "
                + engines.joined(separator: " and ") + ". Restart your Claude Code or Codex sessions to load them."
        } else {
            skillsNote = "The skills didn't update on their own: \(said.isEmpty ? "no reason given" : String(said.suffix(300)))"
        }
    }

    /// What's New's "Update the skills": asks first, then `runway install-skills`, which updates an older install
    /// through each agent's own plugin commands. The check runs again after, so the offer goes away once it's done.
    func updateSkills() {
        guard let cli, let skills = setup?.skills else { return }
        let alert = NSAlert()
        alert.messageText = "Update the Agent Runway skills?"
        alert.informativeText = "Your skills are \(SetupGuide.installedVersions(setup!)); this Runway carries "
            + "\(skills.version ?? "a newer version"). Runway updates them with each agent's own plugin commands "
            + "(claude plugin update, and codex plugin remove then add). Restart Claude Code or Codex sessions "
            + "afterwards to use them."
        alert.addButton(withTitle: "Update the skills")
        alert.addButton(withTitle: "Not now")
        NSApplication.shared.activate(ignoringOtherApps: true)
        guard alert.runModal() == .alertFirstButtonReturn else { return }
        updatingSkills = true
        Task {
            let result = await cli.run(["install-skills"])
            updatingSkills = false
            setupMessage = (result.status == 0 ? result.output : result.error).trimmingCharacters(in: .whitespacesAndNewlines)
            await checkMac()
        }
    }

    /// "What's New…" in the menu: every version up to this one.
    func showAllNotes() {
        whatsNew = WhatsNew.all(current: appVersion, notes: Self.releaseNotes())
    }

    /// "Set it up": each item not there yet, in order, ticked as it lands. A failed item says why and the rest still
    /// run. Then the check again, and the loop starts once the database exists.
    func setUp() async {
        guard let cli, let report = setup else { return }
        installErrors = [:]
        for item in SetupGuide.items(report) where !item.done && !item.skipped {
            installing = item.kind
            let args: [String]
            switch item.kind {
            case .database: args = ["init"]
            case .command: args = ["install-command"]
            case .skills: args = ["install-skills"]
            }
            let result = await cli.run(args)
            if result.status == 0 {
                installed.insert(item.kind)
            } else {
                let said = (result.error.isEmpty ? result.output : result.error)
                installErrors[item.kind] = said.trimmingCharacters(in: .whitespacesAndNewlines)
                    .replacingOccurrences(of: "runway: ", with: "")
            }
        }
        installing = nil
        await checkMac()
        if FileManager.default.fileExists(atPath: Self.databasePath) { startLive(cli) }
    }

    /// The release notes inside Runway.app (copied from app/release-notes), else the repo's when run from a build.
    static func releaseNotes() -> [ReleaseNote] {
        if let bundled = Bundle.main.resourceURL?.appendingPathComponent("release-notes"),
           FileManager.default.fileExists(atPath: bundled.path) {
            return ReleaseNote.load(from: bundled)
        }
        var dir = Bundle.main.executableURL?.deletingLastPathComponent()
        while let current = dir, current.path != "/" {
            let folder = current.appendingPathComponent("release-notes")
            if FileManager.default.fileExists(atPath: current.appendingPathComponent("VERSION").path),
               FileManager.default.fileExists(atPath: folder.path) {
                return ReleaseNote.load(from: folder)
            }
            dir = current.deletingLastPathComponent()
        }
        return []
    }
}
