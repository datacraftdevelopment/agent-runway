import AppKit
import SwiftUI
import RunwayCore

/// The small panel that can float over other apps: what needs you, one card per repo with Start/Stop and what runs
/// where, and the agents' states. "Keep on top" floats it.
struct SidePanel: View {
    let model: AppModel
    @AppStorage("panelKeepOnTop") private var onTop = true
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Runway").font(.system(size: 13, weight: .semibold)).foregroundStyle(Palette.textSoft)
                .frame(maxWidth: .infinity).frame(height: 28).padding(.top, -6)
            if let status = model.status {
                if !status.needsYou.isEmpty { needsYou(status) }
                ScrollView {
                    VStack(spacing: 10) {
                        ForEach(status.repos) { repo in repoCard(repo, status) }
                    }
                }
                .scrollIndicators(.never)
                Spacer(minLength: 0)
                agents(status)
            } else {
                Text(model.loadError ?? "Loading…").foregroundStyle(Palette.textMuted)
                Spacer()
            }
            HStack {
                Toggle("Keep on top", isOn: $onTop).toggleStyle(.checkbox)
                Spacer()
                Button("Full window") {
                    NSApplication.shared.activate(ignoringOtherApps: true)
                    openWindow(id: "runway")
                }
                .buttonStyle(.plain).foregroundStyle(Palette.link)
            }
            .font(.system(size: 12)).foregroundStyle(Palette.textSoft)
            .padding(.horizontal, 4).padding(.top, 6)
        }
        .padding(12)
        .font(.system(size: 13))
        .foregroundStyle(Palette.text)
        .frame(width: 320)
        .frame(minHeight: 560, idealHeight: 640)
        .background(Palette.window)
        .ignoresSafeArea()
        .background(WindowLevel(floating: onTop))
        .preferredColorScheme(.dark)
    }

    private func needsYou(_ status: Status) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            SectionHeading(text: "Needs you · \(status.needsYou.count)", color: Palette.needsYouText)
            ForEach(status.needsYou) { ticket in
                Button {
                    model.select(repo: ticket.repo)
                    model.selectedTicket = ticket.id
                    model.tab = .board
                    NSApplication.shared.activate(ignoringOtherApps: true)
                    openWindow(id: "runway")
                } label: {
                    Text("\(ticket.repo) · \(ticket.question?.short ?? ticket.title) (\(ticket.id))")
                        .foregroundStyle(Palette.text).multilineTextAlignment(.leading)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Palette.needsYouFill, in: RoundedRectangle(cornerRadius: 10))
        .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Palette.needsYouBorder))
    }

    private func repoCard(_ repo: Repo, _ status: Status) -> some View {
        let running = status.tickets(repo: repo.name, in: .running)
        let upNext = status.tickets(repo: repo.name, in: .upNext).count
        let done = status.tickets(repo: repo.name, in: .done).count
        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Dot(color: repo.state.dot)
                Text(repo.name).font(.system(size: 13, weight: .bold))
                Spacer()
                startStop(repo)
            }
            if running.isEmpty {
                Text(upNext > 0 ? "\(repo.statusLine) · \(upNext) up next" : repo.statusLine)
                    .font(.system(size: 12)).foregroundStyle(Palette.textMuted)
            } else {
                VStack(alignment: .leading, spacing: 6) {
                    ForEach(running) { ticket in runningLine(ticket) }
                }
                .font(.system(size: 12))
                Text("\(upNext) up next · \(done) done today").font(.system(size: 11)).foregroundStyle(Palette.textMuted)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Palette.card, in: RoundedRectangle(cornerRadius: 10))
    }

    /// "Mac mini   Codex T-15 reviewing · 14:10"
    private func runningLine(_ ticket: Ticket) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 8) {
            Text(ticket.runsOn ?? "?").foregroundStyle(Palette.place).frame(width: 64, alignment: .leading)
            (Text(ticket.agent.label).foregroundColor(ticket.agent.foreground)
             + Text(" \(ticket.id) \(ticket.stage?.doing ?? "running")")
             + Text(ticket.elapsed.map { " · \(Clock.elapsed($0))" } ?? ""))
                .foregroundStyle(Color(hex: 0xE5E5EA))
        }
    }

    @ViewBuilder private func startStop(_ repo: Repo) -> some View {
        switch repo.state {
        case .running, .needsYou:
            Button("Stop") { model.run(["stop", repo.name]) }.buttonStyle(PlainBoxButtonStyle(fill: Palette.window, small: true))
        case .paused:
            Button("Resume") { model.run(["resume", repo.name]) }.buttonStyle(PrimaryButtonStyle(small: true))
        case .idle, .off:
            Button("Start") { model.run(["start", repo.name]) }.buttonStyle(PrimaryButtonStyle(small: true))
        }
    }

    private func agents(_ status: Status) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(status.agents) { agent in
                (Text(agent.kind.name).foregroundColor(agent.kind.choice.foreground)
                 + Text(agent.restingUntil.map { " resting until \(Clock.time($0)) (usage limit)" } ?? " available"))
            }
        }
        .font(.system(size: 11)).foregroundStyle(Palette.textMuted).padding(.horizontal, 4)
    }
}

/// Sets the hosting window's level, so the panel can float above other apps. From Runway v1.
struct WindowLevel: NSViewRepresentable {
    let floating: Bool

    func makeNSView(context: Context) -> NSView { NSView() }

    func updateNSView(_ view: NSView, context: Context) {
        DispatchQueue.main.async {
            view.window?.level = floating ? .floating : .normal
            view.window?.collectionBehavior.insert(.canJoinAllSpaces)
        }
    }
}
