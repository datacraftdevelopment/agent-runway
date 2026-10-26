import AppKit
import SwiftUI
import RunwayCore

/// The main window: a sidebar of repos, runners and agents; a toolbar; then the Board (four columns and the inspector)
/// or the Activity log. Layout only: every value comes from the status snapshot.
struct MainWindow: View {
    @Bindable var model: AppModel

    var body: some View {
        Group {
            if let status = model.status {
                HStack(spacing: 0) {
                    Sidebar(model: model, status: status)
                    Rectangle().fill(Palette.border).frame(width: 1)
                    VStack(spacing: 0) {
                        Toolbar(model: model, status: status)
                        Rectangle().fill(Palette.border).frame(height: 1)
                        if model.source == .live {
                            AutonomyStrip(model: model)
                            Rectangle().fill(Palette.border).frame(height: 1)
                        }
                        switch model.tab {
                        case .board: BoardView(model: model, status: status)
                        case .activity: ActivityView(status: status, repo: model.selectedRepo)
                        case .stats: StatsTab(model: model)
                        }
                    }
                }
            } else {
                Text(model.loadError ?? "Loading…").foregroundStyle(Palette.textMuted)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            }
        }
        .font(.system(size: 13))
        .foregroundStyle(Palette.text)
        .background(Palette.window)
        .overlay(alignment: .bottom) {
            if let toast = model.toast { ToastView(toast: toast, model: model).padding(.bottom, 22) }
        }
        .sheet(item: $model.confirm) { ConfirmSheet(confirm: $0, model: model) }
        .sheet(item: $model.checkEdit) { CheckSheet(edit: $0, model: model) }
        .ignoresSafeArea()
        .frame(minWidth: 1100, minHeight: 640)
        .preferredColorScheme(.dark)
    }
}

// MARK: Sidebar

private struct Sidebar: View {
    let model: AppModel
    let status: Status
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            // Room for the window's own traffic lights, which sit over the sidebar.
            Color.clear.frame(height: 26)
            SectionHeading(text: "Repos").padding(.horizontal, 8).padding(.vertical, 4)
            ForEach(status.repos) { repo in
                Button { model.select(repo: repo.name) } label: { repoRow(repo) }
                    .buttonStyle(.plain)
                    .contextMenu {
                        MenuItemsView(items: ContextMenus.repo(
                            repo, runners: status.runners,
                            hasDone: !status.tickets(repo: repo.name, in: .done).isEmpty)) { model.perform($0, repo: repo.name) }
                    }
            }
            if let archived = status.archived, !archived.isEmpty {
                ArchivedSection(model: model, archived: archived).padding(.top, 4)
            }
            Spacer(minLength: 12)
            SectionHeading(text: "Where tickets run").padding(.horizontal, 8).padding(.vertical, 4)
            ForEach(status.runners) { runner in
                HStack(spacing: 8) {
                    Dot(color: runner.pausedUntil != nil ? Palette.orange : runner.state.dot)
                    Text(runner.name)
                    Spacer()
                    Text(runner.loadLine).font(.system(size: 11))
                        .foregroundStyle(Palette.textMuted)
                }
                .padding(.horizontal, 8).padding(.vertical, 5)
                .contentShape(Rectangle())
                .contextMenu {
                    MenuItemsView(items: ContextMenus.runner(runner)) { model.perform($0, runner: runner.name) }
                }
            }
            VStack(alignment: .leading, spacing: 3) {
                // Only the engines this Mac has: one is enough.
                ForEach(status.agents) { agent in
                    agentLine(agent.kind.choice, text: agentText(agent, agent.kind))
                }
                agentLine(.any, text: "Any: whichever is free")
            }
            .font(.system(size: 11)).foregroundStyle(Palette.textMuted)
            .padding(.horizontal, 8).padding(.top, 6).padding(.bottom, 8)
            sideButton("Add a repo…", symbol: "plus.circle") {
                // The walkthrough's last step picks the folder and shows the check and session commands it finds.
                model.guideStep = .next
                model.chooseRepo()
                NSApplication.shared.activate(ignoringOtherApps: true)
                openWindow(id: "runway-setup")
            }
            sideButton("Add a Mac or cloud…", symbol: "display") { model.act("Other Macs and cloud come with their runners") }
        }
        .padding(.horizontal, 10).padding(.top, 14).padding(.bottom, 14)
        .frame(width: 220)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(Palette.sidebar)
    }

    private func repoRow(_ repo: Repo) -> some View {
        HStack(spacing: 10) {
            Dot(color: repo.state.dot)
            VStack(alignment: .leading, spacing: 1) {
                Text(repo.name).font(.system(size: 13, weight: .semibold)).foregroundStyle(Palette.text)
                Text(repo.statusLine).font(.system(size: 11)).foregroundStyle(Palette.textMuted)
                HStack(spacing: 4) {
                    Image(systemName: "display").font(.system(size: 9))
                    Text("Main: \(repo.mainComputer)\(repo.runsOn == .main ? " (only)" : "")")
                }
                .font(.system(size: 11)).foregroundStyle(Palette.place)
            }
            Spacer(minLength: 0)
        }
        .padding(8)
        .background(model.selectedRepo == repo.name ? Palette.selectedRow : .clear, in: RoundedRectangle(cornerRadius: 7))
        .contentShape(Rectangle())
    }

    private func agentLine(_ agent: Ticket.AgentChoice, text: String) -> some View {
        HStack(spacing: 6) {
            RoundedRectangle(cornerRadius: 2).fill(agent.swatch).frame(width: 8, height: 8)
            Text(text)
        }
    }

    private func agentText(_ agent: Agent?, _ kind: AgentKind) -> String {
        guard let agent else { return "\(kind.name): not set up" }
        if let until = agent.restingUntil { return "\(kind.name): resting until \(Clock.time(until))" }
        return "\(kind.name): available"
    }

    private func sideButton(_ title: String, symbol: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Image(systemName: symbol).font(.system(size: 12))
                Text(title)
            }
            .foregroundStyle(Palette.textMuted).padding(8).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

// MARK: Toolbar

private struct Toolbar: View {
    @Bindable var model: AppModel
    let status: Status

    var body: some View {
        HStack(spacing: 12) {
            Text(model.selectedRepo ?? "").font(.system(size: 15, weight: .bold))
            if let repo = model.repo { StatusPill(repo: repo, status: status) }
            if model.source == .sample {
                Chip(text: "Sample data", foreground: Palette.needsYouText, background: Palette.needsYouFill)
            }
            Spacer()
            if let action = model.lastAction {
                // The last thing a button did: it gives way (truncates) before the tabs and buttons do.
                Text(action).font(.system(size: 11)).foregroundStyle(Palette.textMuted).lineLimit(1)
                    .truncationMode(.middle).layoutPriority(-1).help(action)
            }
            if let repo = model.repo { runsOnMenu(repo) }
            Segmented(options: [(AppModel.Tab.board, "Board"), (.activity, "Activity"), (.stats, "Stats")],
                      selection: $model.tab)
                .fixedSize()
            Button(model.repo?.state == .paused ? "Resume" : "Pause") {
                model.run([model.repo?.state == .paused ? "resume" : "pause", model.selectedRepo ?? ""])
            }
            .buttonStyle(PlainBoxButtonStyle())
        }
        .padding(.horizontal, 20)
        .frame(height: 56)
    }

    private func runsOnMenu(_ repo: Repo) -> some View {
        Menu {
            Button("Any runner") { model.run(["runs-on", repo.name, "any"]) }
            Button("Main computer only (\(repo.mainComputer))") { model.run(["runs-on", repo.name, "main"]) }
        } label: {
            MenuLabel(prefix: "Runs on", text: repo.runsOn == .any ? "Any runner" : "\(repo.mainComputer) only")
        }
        .menuStyle(.button).buttonStyle(.plain).menuIndicator(.hidden).fixedSize()
    }
}

/// "Running · 3 tickets on 3 runners" in a green capsule; grey or orange for the other states.
struct StatusPill: View {
    let repo: Repo
    let status: Status

    var body: some View {
        let (text, fill, fg) = content
        HStack(spacing: 6) {
            Dot(color: repo.state.dot, size: 7)
            Text(text)
        }
        .font(.system(size: 12)).foregroundStyle(fg)
        .padding(.horizontal, 10).padding(.vertical, 4)
        .background(fill, in: Capsule())
    }

    private var content: (String, Color, Color) {
        switch repo.state {
        case .running:
            let running = status.tickets(repo: repo.name, in: .running)
            let runners = Set(running.compactMap(\.runsOn)).count
            let tickets = running.count == 1 ? "1 ticket" : "\(running.count) tickets"
            let on = runners == 1 ? "1 runner" : "\(runners) runners"
            return ("Running · \(tickets) on \(on)", Palette.runningPillFill, Palette.runningPillText)
        case .needsYou: return ("Needs you", Palette.needsYouFill, Palette.needsYouText)
        case .paused: return (repo.statusLine, Palette.needsYouFill, Palette.needsYouText)
        case .idle: return ("Idle", Palette.selectedRow, Palette.textSoft)
        case .off: return ("Off", Palette.selectedRow, Palette.textSoft)
        }
    }
}

/// A bordered menu button: grey prefix, value, chevron.
struct MenuLabel: View {
    var prefix: String?
    let text: String
    var small = false

    var body: some View {
        HStack(spacing: 6) {
            if let prefix { Text(prefix).foregroundStyle(Palette.textMuted) }
            Text(text).foregroundStyle(Palette.text)
            Image(systemName: "chevron.down").font(.system(size: 8, weight: .semibold)).foregroundStyle(Palette.text)
        }
        .font(.system(size: 12))
        .padding(.horizontal, small ? 8 : 10).padding(.vertical, small ? 3 : 6)
        .background(Palette.control, in: RoundedRectangle(cornerRadius: small ? 5 : 6))
        .overlay(RoundedRectangle(cornerRadius: small ? 5 : 6).strokeBorder(Palette.controlBorder))
    }
}

// MARK: Activity

private struct ActivityView: View {
    let status: Status
    let repo: String?

    var body: some View {
        let lines = status.activity.filter { $0.repo == nil || $0.repo == repo }
        ScrollView {
            VStack(alignment: .leading, spacing: 2) {
                ForEach(lines) { line in
                    HStack(alignment: .firstTextBaseline, spacing: 12) {
                        Text(Clock.time(line.at)).foregroundStyle(Palette.textMuted).frame(width: 44, alignment: .leading)
                        Text(line.kind.label).font(.system(size: 11))
                            .foregroundStyle(line.kind.colors.text)
                            .frame(width: 72).padding(.vertical, 1)
                            .background(line.kind.colors.fill, in: Capsule())
                        Text(line.text).foregroundStyle(Color(hex: 0xE5E5EA))
                    }
                    .padding(.vertical, 4)
                }
            }
            .font(.system(size: 12, design: .monospaced))
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 20).padding(.vertical, 16)
        }
    }
}
