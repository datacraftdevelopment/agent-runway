import AppKit
import SwiftUI
import RunwayCore

/// First run, on one screen, as the design has it:
///   1. What Runway does itself: the command (inside the app), the database, the command in Terminal (asks first), and
///      the skills (said plainly when they don't exist yet).
///   2. This Mac's tools and sign-ins, each missing one with the line that fixes it.
///   3. A first repo: a folder picker, then its check command.
/// Below, the live table of what setup has found per runner. Every check and change is a `runway` command.
struct FirstRunView: View {
    @Bindable var model: AppModel
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Set up Runway").font(.system(size: 20, weight: .bold))
                Text("Runway checks this Mac, shows the fix for anything missing, then watches your first repo.")
                    .foregroundStyle(Palette.textMuted)
            }
            HStack(alignment: .top, spacing: 12) {
                step(1, "Runway does this") { runwayStep }
                step(2, "Check this Mac", highlighted: !(model.setup?.ready ?? false)) { macStep }
                step(3, "Your first repo", highlighted: model.setup?.ready == true && model.setup?.repos.isEmpty == true) {
                    repoStep
                }
            }
            .frame(maxHeight: .infinity, alignment: .top)
            if let message = model.setupMessage {
                Text(message).font(.system(size: 12)).foregroundStyle(Palette.textSoft).lineLimit(3)
                    .textSelection(.enabled)
            }
            found
        }
        .font(.system(size: 13))
        .foregroundStyle(Palette.text)
        .padding(.horizontal, 26).padding(.top, 30).padding(.bottom, 22)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Palette.window)
        .ignoresSafeArea()
        // The hidden title bar adds its 28 points above this, so the window comes out 900 × 660.
        .frame(width: 900, height: 632)
        .preferredColorScheme(.dark)
        .task {
            if model.setup == nil { model.runDoctor() }
            // RUNWAY_PICK=<folder> stands in for the folder picker, for trying step 3 without clicking.
            if let pick = ProcessInfo.processInfo.environment["RUNWAY_PICK"] { model.chooseRepo(at: pick) }
        }
    }

    // MARK: 1. Runway does this

    @ViewBuilder private var runwayStep: some View {
        if let setup = model.setup {
            line(true, "The runway command, inside the app")
            line(true, "The ticket database", detail: shortPath(setup.database))
            if setup.command.linked {
                line(true, "runway in Terminal", detail: shortPath(setup.command.link)
                     + (setup.command.linkDirOnPath ? "" : " (add its folder to PATH)"))
            } else {
                line(false, "runway in Terminal", detail: "optional; asks before adding a link", warn: true)
                Button("Add it to Terminal…") { model.installCommand() }.buttonStyle(PlainBoxButtonStyle(small: true))
            }
            if setup.skills.installed == true {
                line(true, "Runway skills", detail: "map, grill, prototype, spec, file-tickets, runway, setup, take-back")
            } else {
                line(false, "Runway skills", detail: setup.skills.note, warn: true)
                if setup.skills.built {
                    Button("Add the skills…") { model.installSkills() }.buttonStyle(PlainBoxButtonStyle(small: true))
                }
            }
        } else {
            checkingLine
        }
    }

    // MARK: 2. This Mac

    @ViewBuilder private var macStep: some View {
        if let setup = model.setup {
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(setup.tools) { tool in
                        if tool.optional == true {
                            line(false, tool.name, detail: "optional: one engine is enough", warn: true)
                        } else {
                            line(tool.ok, tool.name, detail: tool.ok ? tool.why : nil, fix: tool.fix)
                        }
                    }
                    ForEach(setup.signins) { signin in
                        if signin.optional == true {
                            line(false, "\(signin.label) signed in", detail: "optional", warn: true)
                        } else {
                            line(signin.ok, "\(signin.label) signed in", fix: signin.fix)
                        }
                    }
                    if setup.engines?.isEmpty ?? false {
                        Text("Runway needs Claude Code or Codex, either one, installed and signed in.")
                            .font(.system(size: 11)).foregroundStyle(Palette.needsYouText)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
            .scrollIndicators(.never)
            Button { model.runDoctor() } label: {
                Text(model.checking ? "Checking…" : setup.ready ? "All set · check again" : "Check again")
                    .frame(maxWidth: .infinity)
            }
            .buttonStyle(PlainBoxButtonStyle(fill: Palette.window))
            .disabled(model.checking)
        } else {
            checkingLine
        }
    }

    // MARK: 3. First repo

    @ViewBuilder private var repoStep: some View {
        if let repos = model.setup?.repos, !repos.isEmpty, model.pendingRepo == nil {
            line(true, "Watching \(repos.joined(separator: ", "))")
            Text("In a normal session in that repo, ask your agent to file tickets for Runway (the file-tickets "
                 + "skill); they show up on the board.")
                .foregroundStyle(Palette.textSoft).fixedSize(horizontal: false, vertical: true)
            Button { open("runway") } label: { Text("Open Runway").frame(maxWidth: .infinity) }
                .buttonStyle(PrimaryButtonStyle())
            Button("Add another repo…") { model.chooseRepo() }.buttonStyle(PlainBoxButtonStyle(small: true))
        } else if let repo = model.pendingRepo {
            line(repo.git && repo.slug != nil, repo.name,
                 detail: repo.slug ?? (repo.git ? "no GitHub origin: Runway needs one for pull requests"
                                                : "not a git clone"))
            VStack(alignment: .leading, spacing: 4) {
                Text("Check command (runs before every PR)").font(.system(size: 11)).foregroundStyle(Palette.textMuted)
                TextField("", text: $model.pendingCheck, prompt: Text("e.g. npm test").foregroundStyle(Palette.grey))
                    .textFieldStyle(.plain).font(.system(size: 12, design: .monospaced))
                    .padding(.horizontal, 8).padding(.vertical, 7)
                    .background(Palette.code, in: RoundedRectangle(cornerRadius: 6))
            }
            Button { model.addPendingRepo() } label: { Text("Watch \(repo.name)").frame(maxWidth: .infinity) }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(repo.slug == nil)
            Button("Pick another folder…") { model.chooseRepo() }.buttonStyle(PlainBoxButtonStyle(small: true))
        } else {
            Text("Pick the local clone of a GitHub repo. Runway works in fresh copies of it and never touches your "
                 + "working folder.")
                .foregroundStyle(Palette.textSoft).lineSpacing(3).fixedSize(horizontal: false, vertical: true)
            Button { model.chooseRepo() } label: { Text("Choose a folder…").frame(maxWidth: .infinity) }
                .buttonStyle(PrimaryButtonStyle())
                .disabled(model.setup == nil)
        }
    }

    // MARK: Pieces

    private var checkingLine: some View {
        HStack(spacing: 8) {
            ProgressView().controlSize(.small)
            Text("Checking this Mac…").foregroundStyle(Palette.textSoft)
        }
    }

    private func line(_ ok: Bool, _ title: String, detail: String? = nil, fix: String? = nil,
                      warn: Bool = false) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(ok ? "✓" : warn ? "–" : "✗").foregroundStyle(ok ? Palette.green : warn ? Palette.needsYouText
                                                                  : Color(hex: 0xFF9A94))
            VStack(alignment: .leading, spacing: 3) {
                Text(title).fixedSize(horizontal: false, vertical: true)
                if let detail {
                    Text(detail).font(.system(size: 11)).foregroundStyle(Palette.textMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let fix {
                    HStack(spacing: 6) {
                        Text(fix).font(.system(size: 11, design: .monospaced)).foregroundStyle(Color(hex: 0xE5E5EA))
                            .textSelection(.enabled).lineLimit(2)
                        Button("Copy") { model.copy(fix) }.buttonStyle(.plain).font(.system(size: 11))
                            .foregroundStyle(Palette.link)
                    }
                    .padding(.horizontal, 6).padding(.vertical, 3)
                    .background(Palette.code, in: RoundedRectangle(cornerRadius: 4))
                }
            }
        }
    }

    private func step<Content: View>(_ number: Int, _ title: String, highlighted: Bool = false,
                                     @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(text: "\(number) · \(title)", color: highlighted ? Palette.place : Palette.textMuted)
            content()
            Spacer(minLength: 0)
        }
        .padding(14)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Palette.card, in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(highlighted ? Palette.blue : .clear))
    }

    private var found: some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionHeading(text: "What setup has found so far")
            Grid(alignment: .leading, horizontalSpacing: 8, verticalSpacing: 6) {
                GridRow {
                    Text("").frame(width: 120, alignment: .leading)
                    ForEach(["reachable", "Claude Code", "Codex", "GitHub"], id: \.self) { name in
                        Text(name).foregroundStyle(Palette.textMuted).frame(maxWidth: .infinity, alignment: .leading)
                    }
                }
                ForEach(model.status?.setup ?? []) { row in
                    GridRow {
                        Text(row.runner).fontWeight(.semibold)
                        ForEach(Array([row.reachable, row.claude, row.codex, row.github].enumerated()), id: \.offset) { _, check in
                            Text(check.label).foregroundStyle(check.color)
                        }
                    }
                }
            }
            .font(.system(size: 12))
            Text("Other Macs and the cloud join later; this version runs tickets on this Mac.")
                .font(.system(size: 11)).foregroundStyle(Palette.textMuted)
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Palette.card, in: RoundedRectangle(cornerRadius: 10))
    }

    private func shortPath(_ path: String) -> String {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return path.hasPrefix(home) ? "~" + path.dropFirst(home.count) : path
    }

    private func open(_ id: String) {
        NSApplication.shared.activate(ignoringOtherApps: true)
        openWindow(id: id)
    }
}
