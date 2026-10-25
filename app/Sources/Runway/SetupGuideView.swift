import AppKit
import SwiftUI
import RunwayCore

/// First launch as a short walkthrough in one window: what Runway does, what it found on this Mac, what it will set
/// up (before it does), and what to do next. The rules (where to start, what's missing, what gets installed) are in
/// RunwayCore's SetupGuide; every check and change is a `runway` command.
struct SetupGuideView: View {
    @Bindable var model: AppModel
    @Environment(\.openWindow) private var openWindow
    @Environment(\.dismissWindow) private var dismissWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            progress.padding(.bottom, 22)
            Group {
                switch model.guideStep {
                case .welcome: welcome
                case .check: check
                case .install: install
                case .next: next
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
            if let message = model.setupMessage {
                Text(message).font(.system(size: 12)).foregroundStyle(Palette.textSoft).lineLimit(3)
                    .textSelection(.enabled).padding(.bottom, 10)
            }
            footer
        }
        .font(.system(size: 13))
        .foregroundStyle(Palette.text)
        .padding(.horizontal, 30).padding(.top, 42).padding(.bottom, 24)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
        .background(Palette.window)
        .ignoresSafeArea()
        .frame(width: 760, height: 560)
        .preferredColorScheme(.dark)
        .task {
            if model.setup == nil && !model.checking { await model.checkMac() }
            // RUNWAY_PICK=<folder> stands in for the folder picker, for trying the Next step without clicking.
            if let pick = ProcessInfo.processInfo.environment["RUNWAY_PICK"] { model.chooseRepo(at: pick) }
        }
    }

    // MARK: The steps along the top

    private var progress: some View {
        HStack(spacing: 6) {
            ForEach(SetupGuide.Step.allCases, id: \.self) { step in
                let current = step == model.guideStep, past = step.rawValue < model.guideStep.rawValue
                HStack(spacing: 6) {
                    Text(past ? "✓" : "\(step.rawValue + 1)")
                        .font(.system(size: 11, weight: .bold))
                        .frame(width: 18, height: 18)
                        .background(current ? Palette.blue : past ? Palette.runningPillFill : Palette.control, in: Circle())
                        .foregroundStyle(current ? .white : past ? Palette.runningPillText : Palette.textMuted)
                    Text(step.title).font(.system(size: 12, weight: current ? .semibold : .regular))
                        .foregroundStyle(current ? Palette.text : Palette.textMuted)
                }
                if step != SetupGuide.Step.allCases.last {
                    Rectangle().fill(Palette.controlBorder).frame(width: 22, height: 1)
                }
            }
        }
    }

    // MARK: 1. Welcome

    private var welcome: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Welcome to Runway").font(.system(size: 24, weight: .bold))
            Text("You keep working in Claude Code or Codex as you do now, and file the work as tickets. Runway builds "
                 + "and reviews each one in a fresh copy of your repo: low-risk work merges on its own, and the rest "
                 + "waits for you.")
                .foregroundStyle(Palette.textSoft).lineSpacing(3).fixedSize(horizontal: false, vertical: true)
            HStack(alignment: .top, spacing: 8) {
                flow("You shape it", "in Claude Code or Codex, as you do now")
                arrow
                flow("File tickets", "your agent files them with the file-tickets skill")
                arrow
                flow("Runway builds it", "in a fresh copy, then two reviews")
                arrow
                flow("Merges or asks", "low risk merges on its own; the rest waits for you", highlight: true)
            }
            .padding(.top, 8)
            Text("Setup takes a couple of minutes. Runway checks this Mac first and installs nothing until you say so.")
                .font(.system(size: 12)).foregroundStyle(Palette.textMuted).padding(.top, 6)
        }
    }

    private func flow(_ title: String, _ detail: String, highlight: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title).font(.system(size: 13, weight: .semibold))
            Text(detail).font(.system(size: 11)).foregroundStyle(Palette.textMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .frame(maxWidth: .infinity, minHeight: 92, alignment: .topLeading)
        .background(highlight ? Palette.runningPillFill : Palette.card, in: RoundedRectangle(cornerRadius: 10))
    }

    private var arrow: some View {
        Text("→").foregroundStyle(Palette.textMuted).padding(.top, 36)
    }

    // MARK: 2. Check

    @ViewBuilder private var check: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("What Runway found on this Mac").font(.system(size: 20, weight: .bold))
            if let setup = model.setup {
                HStack(alignment: .top, spacing: 14) {
                    card("An engine · one is enough") {
                        engine("claude", "Claude Code", setup)
                        engine("codex", "Codex", setup)
                        if setup.engines?.isEmpty ?? true {
                            Text("Runway needs one of these installed and signed in. Either is enough.")
                                .font(.system(size: 11)).foregroundStyle(Palette.needsYouText)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    card("Tools") {
                        tool("git", setup)
                        tool("gh", setup, signin: "github")
                        tool("tmux", setup)
                    }
                }
                Text(setup.ready ? "This Mac has what Runway needs."
                                 : "Fix the items marked ✗ (each has the line to run), then check again.")
                    .foregroundStyle(setup.ready ? Palette.green : Palette.textSoft)
            } else {
                checkingLine
            }
        }
    }

    @ViewBuilder private func engine(_ name: String, _ label: String, _ setup: SetupReport) -> some View {
        let tool = setup.tools.first { $0.name == name }
        let signin = setup.signins.first { $0.name == name }
        if signin?.ok == true {
            row(.ok, label, detail: "installed and signed in")
        } else if tool?.optional == true || signin?.optional == true {
            row(.optional, label, detail: "optional: the other engine is ready")
        } else if tool?.ok != true {
            row(.missing, label, detail: "not installed", fix: tool?.fix)
        } else {
            row(.missing, label, detail: "installed, not signed in", fix: signin?.fix)
        }
    }

    @ViewBuilder private func tool(_ name: String, _ setup: SetupReport, signin: String? = nil) -> some View {
        let t = setup.tools.first { $0.name == name }
        let s = signin.flatMap { n in setup.signins.first { $0.name == n } }
        if t?.ok != true {
            row(.missing, name, detail: t?.why, fix: t?.fix)
        } else if let s, !s.ok {
            row(.missing, name, detail: "installed; \(s.label) not signed in", fix: s.fix)
        } else {
            row(.ok, name, detail: (t?.why ?? "") + (s != nil ? ", signed in" : ""))
        }
    }

    // MARK: 3. Set it up

    @ViewBuilder private var install: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("What Runway will set up").font(.system(size: 20, weight: .bold))
            if let setup = model.setup {
                let items = SetupGuide.items(setup)
                Text(items.allSatisfy { $0.done || $0.skipped } ? "Everything is in place."
                     : "Nothing is installed yet. “Set it up” puts these in place, one by one:")
                    .foregroundStyle(Palette.textSoft)
                VStack(alignment: .leading, spacing: 12) {
                    ForEach(items) { item in
                        row(state(item), item.title,
                            detail: model.installErrors[item.kind] ?? (item.skipped
                                ? "Skipped: install Claude Code or Codex first." : item.detail),
                            error: model.installErrors[item.kind] != nil)
                    }
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Palette.card, in: RoundedRectangle(cornerRadius: 10))
                Text("Each one can be undone: the folder is yours to delete, the link is one file, and the skills come "
                     + "out with claude plugin uninstall or codex plugin remove.")
                    .font(.system(size: 11)).foregroundStyle(Palette.textMuted).fixedSize(horizontal: false, vertical: true)
            } else {
                checkingLine
            }
        }
    }

    private func state(_ item: SetupGuide.Item) -> RowState {
        if model.installing == item.kind { return .running }
        if model.installErrors[item.kind] != nil { return .missing }
        if item.done || model.installed.contains(item.kind) { return .ok }
        if item.skipped { return .optional }
        return .pending
    }

    // MARK: 4. Next

    @ViewBuilder private var next: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("You're set. Two things next").font(.system(size: 20, weight: .bold))
            HStack(alignment: .top, spacing: 14) {
                card("1 · Add a repo") { repoStep }
                card("2 · Shape the work and file it") {
                    Text("In your usual Claude Code or Codex session in that repo:")
                        .foregroundStyle(Palette.textSoft).fixedSize(horizontal: false, vertical: true)
                    bullet("Talk the change through and write a short spec with its acceptance checks.")
                    bullet("The file-tickets skill files it as tickets. They show up on the board.")
                    bullet("Ask the runway skill what needs you, or answer on the board.")
                    Text("A first prompt to paste:").font(.system(size: 11)).foregroundStyle(Palette.textMuted)
                        .padding(.top, 4)
                    let prompt = SetupGuide.firstPrompt(repo: model.setup?.repos.first)
                    Text(prompt).font(.system(size: 11, design: .monospaced)).foregroundStyle(Color(hex: 0xE5E5EA))
                        .textSelection(.enabled).fixedSize(horizontal: false, vertical: true)
                        .padding(8).frame(maxWidth: .infinity, alignment: .leading)
                        .background(Palette.code, in: RoundedRectangle(cornerRadius: 6))
                    Button(model.copiedPrompt ? "Copied" : "Copy the prompt") {
                        model.copy(prompt)
                        model.copiedPrompt = true
                    }
                    .buttonStyle(PlainBoxButtonStyle(small: true))
                }
            }
        }
    }

    @ViewBuilder private var repoStep: some View {
        if let repos = model.setup?.repos, !repos.isEmpty, model.pendingRepo == nil {
            row(.ok, "Watching \(repos.joined(separator: ", "))")
            Button("Add another repo…") { model.chooseRepo() }.buttonStyle(PlainBoxButtonStyle(small: true))
        } else if let repo = model.pendingRepo {
            row(repo.git && repo.slug != nil ? .ok : .missing, repo.name,
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
                .buttonStyle(PrimaryButtonStyle()).disabled(repo.slug == nil)
            Button("Pick another folder…") { model.chooseRepo() }.buttonStyle(PlainBoxButtonStyle(small: true))
        } else {
            Text("Pick the local clone of a GitHub repo. Runway works in fresh copies of it and never touches your "
                 + "working folder.")
                .foregroundStyle(Palette.textSoft).lineSpacing(3).fixedSize(horizontal: false, vertical: true)
            Button { model.chooseRepo() } label: { Text("Choose a folder…").frame(maxWidth: .infinity) }
                .buttonStyle(PrimaryButtonStyle())
        }
    }

    // MARK: Back and forward

    private var footer: some View {
        HStack {
            if model.guideStep != .welcome {
                Button("Back") { go(-1) }.buttonStyle(PlainBoxButtonStyle())
            }
            Spacer()
            switch model.guideStep {
            case .welcome:
                Button("Get started") { go(1) }.buttonStyle(PrimaryButtonStyle())
            case .check:
                Button(model.checking ? "Checking…" : "Check again") { Task { await model.checkMac() } }
                    .buttonStyle(PlainBoxButtonStyle()).disabled(model.checking)
                let ready = model.setup.map(SetupGuide.macReady) ?? false
                Button("Continue") { go(1) }.buttonStyle(PrimaryButtonStyle())
                    .disabled(!ready).opacity(ready ? 1 : 0.4)
            case .install:
                if let setup = model.setup,
                   SetupGuide.items(setup).allSatisfy({ $0.done || $0.skipped || model.installed.contains($0.kind) }),
                   model.installing == nil {
                    Button("Continue") { go(1) }.buttonStyle(PrimaryButtonStyle())
                } else {
                    Button(model.installing != nil ? "Setting up…" : model.installErrors.isEmpty ? "Set it up" : "Try again") {
                        Task { await model.setUp() }
                    }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(model.installing != nil || model.setup == nil)
                    .opacity(model.installing != nil ? 0.6 : 1)
                }
            case .next:
                Button("Open Runway") {
                    NSApplication.shared.activate(ignoringOtherApps: true)
                    openWindow(id: "runway")
                    dismissWindow(id: "runway-setup")
                }
                .buttonStyle(PrimaryButtonStyle())
            }
        }
    }

    private func go(_ by: Int) {
        if let step = SetupGuide.Step(rawValue: model.guideStep.rawValue + by) { model.guideStep = step }
    }

    // MARK: Pieces

    enum RowState { case ok, missing, optional, pending, running }

    private var checkingLine: some View {
        HStack(spacing: 8) {
            ProgressView().controlSize(.small)
            Text("Checking this Mac…").foregroundStyle(Palette.textSoft)
        }
    }

    private func card<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(text: title)
            content()
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(Palette.card, in: RoundedRectangle(cornerRadius: 10))
    }

    private func bullet(_ text: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text("•").foregroundStyle(Palette.textMuted)
            Text(text).fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder private func mark(_ state: RowState) -> some View {
        switch state {
        case .ok: Text("✓").foregroundStyle(Palette.green)
        case .missing: Text("✗").foregroundStyle(Color(hex: 0xFF9A94))
        case .optional: Text("–").foregroundStyle(Palette.needsYouText)
        case .pending: Text("○").foregroundStyle(Palette.textMuted)
        case .running: ProgressView().controlSize(.mini)
        }
    }

    private func row(_ state: RowState, _ title: String, detail: String? = nil, fix: String? = nil,
                     error: Bool = false) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            mark(state).frame(width: 14)
            VStack(alignment: .leading, spacing: 3) {
                Text(title).fixedSize(horizontal: false, vertical: true)
                if let detail {
                    Text(detail).font(.system(size: 11))
                        .foregroundStyle(error ? Color(hex: 0xFF9A94) : Palette.textMuted)
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
}
