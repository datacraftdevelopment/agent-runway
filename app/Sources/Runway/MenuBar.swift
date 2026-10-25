import AppKit
import SwiftUI
import RunwayCore

/// The menu bar icon: an airplane, plus the needs-you count when something is waiting.
struct MenuBarLabel: View {
    let model: AppModel

    var body: some View {
        let count = model.status?.needsYou.count ?? 0
        HStack(spacing: 3) {
            Image(systemName: count > 0 ? "airplane.departure" : "airplane")
            if count > 0 { Text("\(count)") }
        }
    }
}

/// What drops down from the menu bar: needs you, the repos, pause, open the panel or window, quit.
struct MenuBarContent: View {
    let model: AppModel
    /// Set when the menu closes itself after a click; nil when it is drawn in a plain window (screenshots).
    var dismiss: (() -> Void)?
    @Environment(\.openWindow) private var openWindow
    @State private var hovered: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            if let status = model.status {
                if !status.needsYou.isEmpty {
                    SectionHeading(text: "Needs you", color: Palette.needsYouText).padding(.horizontal, 8).padding(.vertical, 6)
                    ForEach(status.needsYou) { ticket in
                        item(id: "ny-\(ticket.id)") {
                            show(ticket)
                        } label: {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(ticket.question?.short ?? ticket.title)
                                Text("\(ticket.repo) · \(ticket.id)").font(.system(size: 11)).foregroundStyle(Palette.textMuted)
                            }
                        }
                    }
                    divider
                }
                ForEach(status.repos) { repo in
                    item(id: "repo-\(repo.name)") {
                        model.select(repo: repo.name)
                        open("runway")
                    } label: {
                        HStack(spacing: 8) {
                            Dot(color: repo.state.dot)
                            Text(repo.name)
                            Spacer()
                            Text(repoNote(repo, status)).font(.system(size: 11)).foregroundStyle(Palette.textMuted)
                        }
                    }
                }
                divider
            } else {
                Text(model.loadError ?? "Loading…").foregroundStyle(Palette.textMuted).padding(8)
            }
            item(id: "pause") { model.run(["pause", "--for", "1h"]) } label: { Text("Pause everything for 1 hour") }
            item(id: "panel") { open("runway-panel") } label: { Text("Open side panel") }
            item(id: "window") { open("runway") } label: { Text("Open Runway") }
            item(id: "setup") {
                model.guideStep = model.setup.map { SetupGuide.start($0, firstLaunch: false) } ?? .check
                open("runway-setup")
            } label: { Text("Set up Runway…") }
            item(id: "whatsnew") {
                model.showAllNotes()
                open("runway-whatsnew")
            } label: { Text("What's New…") }
            divider
            if let note = AppUpdater.shared.state.menuNote {
                Text("Runway \(AppUpdater.shared.version) · \(note)")
                    .font(.system(size: 11)).foregroundStyle(Palette.textMuted).padding(.horizontal, 8).padding(.vertical, 6)
            } else {
                item(id: "updates") {
                    dismiss?()
                    NSApplication.shared.activate(ignoringOtherApps: true)
                    AppUpdater.shared.checkForUpdates()
                } label: {
                    HStack {
                        Text("Check for Updates…")
                        Spacer()
                        Text(AppUpdater.shared.version).font(.system(size: 11)).foregroundStyle(Palette.textMuted)
                    }
                }
            }
            item(id: "quit") { NSApplication.shared.terminate(nil) } label: {
                Text("Quit (running tickets keep going)").foregroundStyle(Palette.textMuted)
            }
        }
        .font(.system(size: 13))
        .foregroundStyle(Palette.text)
        .padding(6)
        .frame(width: 300)
        .background(Palette.card)
        .preferredColorScheme(.dark)
    }

    private var divider: some View {
        Rectangle().fill(Palette.controlBorder).frame(height: 1).padding(.horizontal, 6).padding(.vertical, 4)
    }

    private func item<Label: View>(id: String, action: @escaping () -> Void,
                                   @ViewBuilder label: () -> Label) -> some View {
        Button(action: action) {
            label()
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 8).padding(.vertical, 6)
                .background(hovered == id || (dismiss == nil && id.hasPrefix("ny-") && isFirstNeedsYou(id))
                            ? Palette.selectedRow : .clear,
                            in: RoundedRectangle(cornerRadius: 6))
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .onHover { hovered = $0 ? id : (hovered == id ? nil : hovered) }
    }

    /// The window-drawn copy highlights the first needs-you row, as the mock does, so the hover look shows.
    private func isFirstNeedsYou(_ id: String) -> Bool {
        hovered == nil && model.status?.needsYou.first.map { "ny-\($0.id)" } == id
    }

    private func repoNote(_ repo: Repo, _ status: Status) -> String {
        switch repo.state {
        case .running:
            let running = status.tickets(repo: repo.name, in: .running).count
            return "\(running) running"
        case .needsYou: return "needs you"
        case .paused: return "paused"
        case .idle: return "idle"
        case .off: return "off"
        }
    }

    private func show(_ ticket: Ticket) {
        model.select(repo: ticket.repo)
        model.selectedTicket = ticket.id
        model.tab = .board
        open("runway")
    }

    private func open(_ id: String) {
        dismiss?()
        NSApplication.shared.activate(ignoringOtherApps: true)
        openWindow(id: id)
    }
}
