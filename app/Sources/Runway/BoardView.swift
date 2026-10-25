import SwiftUI
import RunwayCore

/// Needs you, Up next, Running, Done, then the inspector for the clicked card. No drag and drop: moving a card is
/// never a go.
struct BoardView: View {
    let model: AppModel
    let status: Status

    var body: some View {
        HStack(spacing: 0) {
            HStack(alignment: .top, spacing: 12) {
                ForEach(Ticket.Column.allCases, id: \.self) { column in
                    columnView(column)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            Rectangle().fill(Palette.border).frame(width: 1)
            Inspector(model: model, status: status)
        }
    }

    private func columnView(_ column: Ticket.Column) -> some View {
        let tickets = status.tickets(repo: model.selectedRepo ?? "", in: column)
        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Dot(color: column.dot)
                Text(column.title).font(.system(size: 12, weight: .bold))
                Text("\(tickets.count)").font(.system(size: 12)).foregroundStyle(Palette.textMuted)
            }
            .padding(.horizontal, 4).padding(.top, 2).padding(.bottom, 6)
            ScrollView {
                VStack(spacing: 8) {
                    ForEach(tickets) { ticket in
                        Button { model.selectedTicket = ticket.id } label: {
                            TicketCard(ticket: ticket, selected: model.selectedTicket == ticket.id)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .scrollIndicators(.never)
        }
        .frame(maxWidth: .infinity, alignment: .topLeading)
    }
}

struct TicketCard: View {
    let ticket: Ticket
    let selected: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(ticket.title).font(.system(size: 13, weight: .semibold)).foregroundStyle(Palette.text)
                .lineSpacing(2).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
            Text("\(ticket.id) · \(ticket.placeLine)").font(.system(size: 11)).foregroundStyle(Palette.textMuted)
            if ticket.column == .running, let stage = ticket.stage { StageBar(stage: stage) }
            HStack(spacing: 4) {
                AgentChip(agent: ticket.agent)
                RiskChip(risk: ticket.risk)
                if ticket.kind == "retro" {
                    Chip(text: "retro", foreground: Color(hex: 0xD5B3FF), background: Color(hex: 0x2D2140))
                }
                if ticket.taken == true {
                    Chip(text: ticket.takenLong ? "taken back · \(Int((ticket.takenHours ?? 0) / 24))d" : "taken back",
                         foreground: Palette.needsYouText, background: Palette.needsYouFill)
                        .help(ticket.takenLong ? "Taken back more than a day ago: give it back, mark it done, or drop it"
                              : "Taken back")
                }
            }
        }
        .padding(.horizontal, 12).padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Palette.card, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(selected ? Palette.blue : Palette.border,
                                                                lineWidth: selected ? 2 : 1))
        .contentShape(Rectangle())
    }
}

/// The clicked ticket: its fields, a Runs on menu, the Needs-you box with a note and Go/No, and Open session.
private struct Inspector: View {
    let model: AppModel
    let status: Status
    @State private var note = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let ticket = model.ticket {
                content(ticket)
            } else {
                Text("Pick a card").foregroundStyle(Palette.textMuted)
                Spacer()
            }
        }
        .padding(18)
        .frame(width: 320)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(Palette.inspector)
        .onChange(of: model.selectedTicket) { note = "" }
    }

    @ViewBuilder private func content(_ ticket: Ticket) -> some View {
        Text("\(ticket.id) · \(ticket.column.title)").font(.system(size: 11)).foregroundStyle(Palette.textMuted)
        Text(ticket.title).font(.system(size: 16, weight: .bold)).lineSpacing(2)
            .fixedSize(horizontal: false, vertical: true)
        VStack(alignment: .leading, spacing: 6) {
            row("Filed", "\(ticket.filedFrom), \(Clock.time(ticket.filedAt))")
            row("Agent", ticket.agent.longLabel)
            HStack(alignment: .firstTextBaseline, spacing: 0) {
                label("Runs on")
                runsOnMenu(ticket)
            }
            row("Risk", ticket.risk.longLabel)
            HStack(alignment: .firstTextBaseline, spacing: 0) {
                label("PR")
                if let pr = ticket.pr {
                    Button(pr) { model.openPR(ticket) }.buttonStyle(.plain)
                        .foregroundStyle(Palette.link)
                } else {
                    Text("not opened")
                }
            }
            row("Code review", ticket.review ?? "not yet")
            row("Function review", ticket.functionReview ?? "not yet")
            if !ticket.waitsOn.isEmpty { row("Waits on", ticket.waitsOn.joined(separator: ", ")) }
        }
        .font(.system(size: 12))
        if ticket.column == .needsYou, ticket.taken != true, let question = ticket.question { needsYou(ticket, question) }
        if ticket.takenLong {
            Text("Taken back \(Int((ticket.takenHours ?? 0) / 24)) day(s) ago and still open. Finish it with the "
                 + "take-back skill: give it back, mark it done, or drop it.")
                .font(.system(size: 12)).foregroundStyle(Palette.textMuted)
                .fixedSize(horizontal: false, vertical: true)
        }
        if let summary = ticket.summary {
            Text(summary).font(.system(size: 12)).foregroundStyle(Palette.textSoft).lineSpacing(3)
                .fixedSize(horizontal: false, vertical: true)
        }
        Spacer()
        if let runs = ticket.retroRuns, !runs.isEmpty { runsBehind(runs) }
        if let prompt = model.takePrompts[ticket.id] { takePrompt(prompt) }
        if ticket.column != .done {
            HStack(spacing: 8) {
                Button { model.takeBack(ticket.id) } label: {
                    Text(ticket.taken == true ? "Copy prompt again" : "Take back · copy prompt").frame(maxWidth: .infinity)
                }
                .buttonStyle(TakeBackButtonStyle())
                .help("Stops its worker, keeps its branch and copies a prompt for any Claude Code or Codex session")
                Button { model.run(["give", ticket.id]) } label: {
                    Text("Give back").frame(maxWidth: .infinity)
                }
                .buttonStyle(PlainBoxButtonStyle())
                .disabled(ticket.taken != true)
                .help("Pushes your commits and queues it again; both reviews run on your commit")
            }
        }
    }

    /// A retro's failing runs, each linked to its PR when it has one.
    private func runsBehind(_ runs: [Ticket.RetroRun]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            SectionHeading(text: "Runs behind this", color: Color(hex: 0xD5B3FF))
            ForEach(runs, id: \.ticket) { run in
                if let url = run.prUrl.flatMap(URL.init(string:)) {
                    Link("\(run.ticket) · \(run.title)", destination: url).foregroundStyle(Palette.link)
                } else {
                    Text("\(run.ticket) · \(run.title)").foregroundStyle(Palette.textSoft)
                        .help(run.record ?? "")
                }
            }
        }
        .font(.system(size: 12))
        .padding(.horizontal, 12).padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(hex: 0x2D2140), in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Color(hex: 0x4B3570)))
    }

    private func takePrompt(_ prompt: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                SectionHeading(text: "Take-back prompt", color: Palette.needsYouText)
                Spacer()
                Text("✓ Copied. Paste it into Claude Code or Codex.").font(.system(size: 11))
                    .foregroundStyle(Palette.runningPillText)
            }
            ScrollView {
                Text(prompt).font(.system(size: 10.5, design: .monospaced)).foregroundStyle(Color(hex: 0xE5E5EA))
                    .lineSpacing(2).textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
            }
            .frame(maxHeight: 180)
            .padding(.horizontal, 10).padding(.vertical, 8)
            .background(Palette.code, in: RoundedRectangle(cornerRadius: 6))
            .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Palette.border))
        }
    }

    private func needsYou(_ ticket: Ticket, _ question: Ticket.Question) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(text: "Needs you", color: Palette.needsYouText)
            Text(question.text).font(.system(size: 13)).lineSpacing(3).fixedSize(horizontal: false, vertical: true)
            VStack(alignment: .leading, spacing: 4) {
                Text("Note (optional)").font(.system(size: 11)).foregroundStyle(Palette.textMuted)
                TextField("", text: $note, prompt: Text("Anything the agent should know").foregroundStyle(Palette.grey))
                    .textFieldStyle(.plain).font(.system(size: 12))
                    .padding(.horizontal, 8).padding(.vertical, 7)
                    .background(Palette.window, in: RoundedRectangle(cornerRadius: 6))
                    .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Palette.controlBorder))
            }
            HStack(spacing: 8) {
                Button { model.run(["go", ticket.id] + (note.isEmpty ? [] : ["--note", note])) } label: {
                    Text(question.goLabel).frame(maxWidth: .infinity)
                }
                .buttonStyle(PrimaryButtonStyle())
                Button { model.run(["no", ticket.id] + (note.isEmpty ? [] : ["--note", note])) } label: {
                    Text(question.noLabel).frame(maxWidth: .infinity).padding(.vertical, 2)
                }
                .buttonStyle(PlainBoxButtonStyle())
            }
        }
        .padding(12)
        .background(Palette.needsYouFill, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Palette.needsYouBorder))
    }

    private func runsOnMenu(_ ticket: Ticket) -> some View {
        Menu {
            Button("Any free runner") { model.run(["runs-on", ticket.id, "any"]) }
            Divider()
            ForEach(status.runners) { runner in
                Button("\(runner.name) only") { model.run(["runs-on", ticket.id, runner.name]) }
            }
        } label: {
            MenuLabel(text: ticket.placeLine, small: true)
        }
        .menuStyle(.button).buttonStyle(.plain).menuIndicator(.hidden).fixedSize()
    }

    private func row(_ name: String, _ value: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 0) {
            label(name)
            Text(value).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
    }

    private func label(_ name: String) -> some View {
        Text(name).foregroundStyle(Palette.textMuted).frame(width: 104, alignment: .leading)
    }
}
