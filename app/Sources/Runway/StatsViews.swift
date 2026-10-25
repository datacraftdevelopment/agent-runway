import SwiftUI
import RunwayCore

/// The strip under the toolbar: how hands-off the last 7 (or 30) days were, for the selected repo.
struct AutonomyStrip: View {
    @Bindable var model: AppModel

    var body: some View {
        let scope = model.stats?.scope(repo: model.selectedRepo)
        let w = scope?.window(model.statsDays)
        FlowLayout(spacing: 22, lineSpacing: 6) {
            Button { model.statsDays = model.statsDays == 7 ? 30 : 7 } label: {
                SectionHeading(text: "Last \(model.statsDays) days")
            }
            .buttonStyle(.plain).help("Switch between 7 and 30 days")
            if let w {
                if w.merged == 0 {
                    Text("Nothing merged yet").foregroundStyle(Palette.textMuted)
                } else {
                    (Text("Hands-off ").foregroundColor(Palette.textMuted)
                     + Text("\(w.handsOff) of \(w.merged)").bold().foregroundColor(Palette.runningPillText)
                        .font(.system(size: 14))
                     + Text(" merged (\(percent(w.handsOffRate)))").foregroundColor(Palette.textMuted))
                    (Text("Cycle time ").foregroundColor(Palette.textMuted)
                     + Text(StatsFormat.minutes(w.cycleMinutes.handsOff)).bold()
                     + Text(" hands-off · \(StatsFormat.minutes(w.cycleMinutes.rest)) the rest")
                        .foregroundColor(Palette.textMuted))
                    cost(w.costPerTicket)
                }
                if !w.stopped.isEmpty {
                    (Text("Stopped for you: ").foregroundColor(Palette.textMuted)
                     + Text(w.stopped.prefix(4).map { "\($0.label) \($0.count)" }.joined(separator: " · ")))
                }
            } else {
                Text(model.source == .live ? "Reading stats…" : "Stats come from the live runway command")
                    .foregroundStyle(Palette.textMuted)
            }
        }
        .font(.system(size: 12))
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 20).padding(.vertical, 10)
        .background(Palette.inspector)
    }

    private func percent(_ rate: Double?) -> String {
        rate.map { "\(Int(($0 * 100).rounded()))%" } ?? "–"
    }

    /// "$0.84 Claude · 41k tokens Codex": dollars only where the engine reports them.
    private func cost(_ c: StatsSnapshot.Cost) -> some View {
        let parts = c.byAgent.map { a -> Text in
            let value = a.medianUsd.map(StatsFormat.dollars) ?? StatsFormat.tokens(a.medianTokens)
            return Text(value).bold().foregroundColor(a.agent.choice.foreground)
                + Text(" \(a.agent == .claude ? "Claude" : "Codex")").foregroundColor(Palette.textMuted)
        }
        return parts.enumerated().reduce(Text("Cost per ticket ").foregroundColor(Palette.textMuted)) { acc, item in
            acc + (item.offset == 0 ? Text("") : Text(" · ").foregroundColor(Palette.textMuted)) + item.element
        }
    }
}

/// The Stats tab: where tickets stopped for the person (30 days), and the head-to-head table.
struct StatsTab: View {
    let model: AppModel

    var body: some View {
        let scope = model.stats?.scope(repo: model.selectedRepo)
        HStack(alignment: .top, spacing: 16) {
            card("Where tickets stopped for you · 30 days") {
                let stops = scope?.window(30)?.stopped ?? []
                if stops.isEmpty {
                    Text("Nothing has stopped for you yet.").foregroundStyle(Palette.textMuted)
                }
                let most = max(stops.map(\.count).max() ?? 1, 1)
                ForEach(stops, id: \.reason) { stop in
                    HStack(spacing: 10) {
                        Text(stop.label.prefix(1).uppercased() + stop.label.dropFirst())
                            .foregroundStyle(Color(hex: 0xE5E5EA)).frame(width: 190, alignment: .leading)
                        Capsule().fill(Palette.blue).frame(width: CGFloat(stop.count) / CGFloat(most) * 160, height: 8)
                        Text("\(stop.count)").foregroundStyle(Palette.textMuted)
                    }
                }
                Text("3 of the same reason in 7 days files a retro ticket (not low risk, never merges itself).")
                    .font(.system(size: 11)).foregroundStyle(Palette.textMuted).padding(.top, 4)
            }
            card("Head-to-head on done tickets") {
                if (model.status?.agents.count ?? 0) < 2 {
                    Text("Needs both Claude Code and Codex signed in. With one engine, everything else works as "
                         + "normal: two fresh review sessions on that engine.")
                        .foregroundStyle(Palette.textSoft).lineSpacing(3).fixedSize(horizontal: false, vertical: true)
                } else if let rows = model.stats?.bench, !rows.isEmpty {
                    benchTable(rows)
                    Text("Runs only when you start it (runway bench <T-n>); never pushes. Uses both subscriptions.")
                        .font(.system(size: 11)).foregroundStyle(Palette.textMuted)
                } else {
                    Text("Nothing compared yet. Run runway bench <T-n> --agents claude,codex on done tickets; it "
                         + "never pushes, and uses both subscriptions.")
                        .foregroundStyle(Palette.textSoft).lineSpacing(3).fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .font(.system(size: 12))
        .padding(.horizontal, 20).padding(.vertical, 18)
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    private func benchTable(_ rows: [StatsSnapshot.BenchRow]) -> some View {
        Grid(alignment: .leading, horizontalSpacing: 10, verticalSpacing: 6) {
            GridRow {
                ForEach(["ticket", "agent", "result", "time · cost"], id: \.self) {
                    Text($0).foregroundStyle(Palette.textMuted)
                }
            }
            ForEach(Array(rows.enumerated()), id: \.offset) { i, row in
                GridRow {
                    Text(i > 0 && rows[i - 1].ticket == row.ticket ? "" : "\(row.ticket) \(row.title)").lineLimit(1)
                    Text(row.agent == .claude ? "Claude" : "Codex").foregroundStyle(row.agent.choice.foreground)
                    Text(row.result).foregroundStyle(row.result == "pass" ? Color(hex: 0x7EE59A) : Color(hex: 0xFF9FBF))
                        .help(row.why ?? "")
                    Text(StatsFormat.minutes(row.minutes) + " · "
                         + (row.costUsd.map(StatsFormat.dollars) ?? StatsFormat.tokens(row.tokens)))
                }
            }
        }
    }

    private func card<Content: View>(_ title: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionHeading(text: title)
            content()
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .topLeading)
        .background(Palette.card, in: RoundedRectangle(cornerRadius: 10))
    }
}

/// Lays its children out left to right and wraps to a new line when the next one doesn't fit, like CSS flex-wrap.
struct FlowLayout: Layout {
    var spacing: CGFloat = 8
    var lineSpacing: CGFloat = 4

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        let height = rows.map(\.height).reduce(0, +) + lineSpacing * CGFloat(max(rows.count - 1, 0))
        return CGSize(width: proposal.width ?? rows.map(\.width).max() ?? 0, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(width: bounds.width, subviews: subviews) {
            var x = bounds.minX
            for index in row.items {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: y + (row.height - size.height) / 2), proposal: .unspecified)
                x += size.width + spacing
            }
            y += row.height + lineSpacing
        }
    }

    private struct Row { var items: [Int] = []; var width: CGFloat = 0; var height: CGFloat = 0 }

    private func arrange(width: CGFloat, subviews: Subviews) -> [Row] {
        var rows = [Row()]
        for index in subviews.indices {
            let size = subviews[index].sizeThatFits(.unspecified)
            let extra = rows[rows.count - 1].items.isEmpty ? size.width : size.width + spacing
            if rows[rows.count - 1].width + extra > width, !rows[rows.count - 1].items.isEmpty {
                rows.append(Row())
            }
            let gap = rows[rows.count - 1].items.isEmpty ? 0 : spacing
            rows[rows.count - 1].items.append(index)
            rows[rows.count - 1].width += size.width + gap
            rows[rows.count - 1].height = max(rows[rows.count - 1].height, size.height)
        }
        return rows
    }
}
