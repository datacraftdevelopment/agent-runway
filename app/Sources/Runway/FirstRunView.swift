import AppKit
import SwiftUI
import RunwayCore

/// First run, on one screen: what Runway did itself, the agent that finishes setup, more places to run, and a live
/// table of what setup has found per runner (from the status file's `setup` rows).
struct FirstRunView: View {
    let model: AppModel
    @State private var agent: AgentKind = .claude
    @State private var copied = false

    /// What the app lays down before handing over. Fixed text until Phase 3 makes these real steps.
    private let done = ["Installed the runway command", "Created the ticket database",
                        "Added the Runway skills to Claude Code", "Added the Runway skills to Codex"]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Set up Runway").font(.system(size: 20, weight: .bold))
                Text("Runway lays the groundwork; your agent finishes the setup on each computer.")
                    .foregroundStyle(Palette.textMuted)
            }
            HStack(alignment: .top, spacing: 12) {
                step(1, "Runway does this") {
                    ForEach(done, id: \.self) { line in
                        HStack(alignment: .firstTextBaseline, spacing: 8) {
                            Text("✓").foregroundStyle(Palette.green)
                            Text(line).fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
                step(2, "Your agent finishes", highlighted: true) {
                    Segmented(options: [(AgentKind.claude, "Claude Code"), (.codex, "Codex")], selection: $agent,
                              stretch: true)
                    Text("It checks the sign-ins, adds this Mac as a place tickets run, and asks which repos to watch.")
                        .foregroundStyle(Palette.textSoft).lineSpacing(3).fixedSize(horizontal: false, vertical: true)
                    CodeLine(text: setupCommand)
                    Button { model.act("open \(agent.name) on setup: \(setupCommand)") } label: {
                        Text("Open \(agent.name)").frame(maxWidth: .infinity)
                    }
                    .buttonStyle(PrimaryButtonStyle())
                }
                step(3, "More places to run") {
                    Text("On each other Mac, run the same setup with “join”. For cloud, the agent connects your Claude and Codex cloud accounts.")
                        .foregroundStyle(Palette.textSoft).lineSpacing(3).fixedSize(horizontal: false, vertical: true)
                    CodeLine(text: joinCommand)
                    Button {
                        NSPasteboard.general.clearContents()
                        NSPasteboard.general.setString(joinCommand, forType: .string)
                        copied = true
                        model.act("copied: \(joinCommand)")
                    } label: {
                        Text(copied ? "Copied" : "Copy").frame(maxWidth: .infinity).padding(.vertical, 2)
                    }
                    .buttonStyle(PlainBoxButtonStyle(fill: Palette.window))
                }
            }
            .frame(maxHeight: .infinity, alignment: .top)
            found
        }
        .font(.system(size: 13))
        .foregroundStyle(Palette.text)
        .padding(.horizontal, 26).padding(.top, 30).padding(.bottom, 22)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(Palette.window)
        .ignoresSafeArea()
        // The hidden title bar adds its 28 points above this, so the window comes out 760 × 580 as in the mock.
        .frame(width: 760, height: 552)
        .preferredColorScheme(.dark)
        .onChange(of: agent) { copied = false }
    }

    private var setupCommand: String { agent == .claude ? #"claude "/runway:setup""# : #"codex "$runway-setup""# }
    private var joinCommand: String { agent == .claude ? #"claude "/runway:setup join""# : #"codex "$runway-setup join""# }

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
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Palette.card, in: RoundedRectangle(cornerRadius: 10))
    }
}

private struct CodeLine: View {
    let text: String

    var body: some View {
        Text(text).font(.system(size: 12, design: .monospaced)).foregroundStyle(Color(hex: 0xE5E5EA))
            .textSelection(.enabled)
            .padding(8).frame(maxWidth: .infinity, alignment: .leading)
            .background(Palette.code, in: RoundedRectangle(cornerRadius: 6))
    }
}
