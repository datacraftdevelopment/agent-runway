import SwiftUI
import RunwayCore

/// Needs you, Up next, Running, Done, then the inspector for the clicked card. No drag and drop: moving a card is
/// never a go.
struct BoardView: View {
    let model: AppModel
    let status: Status

    var body: some View {
        HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 12) {
                if let repo = model.repo, let why = repo.idleReason { idleBanner(why, repo.idleTicket) }
                if let repo = model.repo, repo.checkCmd == nil, model.source == .live { noCheckBanner(repo.name) }
                HStack(alignment: .top, spacing: 12) {
                    ForEach(Ticket.Column.allCases, id: \.self) { column in
                        columnView(column)
                    }
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
            Rectangle().fill(Palette.border).frame(width: 1)
            Inspector(model: model, status: status)
        }
    }

    /// A repo with no check command: Runway's sessions can't run its tests or builds, so reviews can't pass.
    private func noCheckBanner(_ repo: String) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "exclamationmark.triangle").foregroundStyle(Palette.needsYouText)
            Text("No check command set: Runway's sessions can't run \(repo)'s tests or builds.")
            Spacer(minLength: 0)
            Button("Set check command…") { model.openCheck(repo) }.buttonStyle(PlainBoxButtonStyle(small: true))
        }
        .font(.system(size: 12))
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(Palette.needsYouFill, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Palette.needsYouBorder))
    }

    /// Why nothing in Up next is starting, with the ticket to look at (or the loop to start).
    private func idleBanner(_ why: String, _ ticket: String?) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "pause.circle").foregroundStyle(Palette.needsYouText)
            Text(why).foregroundStyle(Palette.text)
            Spacer(minLength: 0)
            if let ticket {
                Button("Show \(ticket)") { model.selectedTicket = ticket }.buttonStyle(PlainBoxButtonStyle(small: true))
            } else if status.loopRunning == false {
                Button("Start the loop") { model.restartLoop() }.buttonStyle(PlainBoxButtonStyle(small: true))
            }
        }
        .font(.system(size: 12))
        .padding(.horizontal, 12).padding(.vertical, 8)
        .background(Palette.needsYouFill, in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(Palette.needsYouBorder))
    }

    private func columnView(_ column: Ticket.Column) -> some View {
        let tickets = status.tickets(repo: model.selectedRepo ?? "", in: column)
        return VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Dot(color: column.dot)
                Text(column.title).font(.system(size: 12, weight: .bold))
                Text("\(tickets.count)").font(.system(size: 12)).foregroundStyle(Palette.textMuted)
                if column == .done, !tickets.isEmpty, let repo = model.selectedRepo {
                    Spacer()
                    Button("Clear done") { model.clearDone(repo) }.buttonStyle(.plain)
                        .font(.system(size: 11)).foregroundStyle(Palette.link)
                        .help("Takes the done tickets off the board. They still count in stats; Undo puts them back.")
                }
            }
            .padding(.horizontal, 4).padding(.top, 2).padding(.bottom, 6)
            ScrollView {
                VStack(spacing: 8) {
                    ForEach(tickets) { ticket in
                        Button { model.selectedTicket = ticket.id } label: {
                            TicketCard(ticket: ticket, selected: model.selectedTicket == ticket.id) {
                                model.selectedTicket = $0
                            }
                        }
                        .buttonStyle(.plain)
                        .contextMenu {
                            MenuItemsView(items: ContextMenus.ticket(ticket, runners: status.runners)) {
                                model.perform($0, ticket: ticket)
                            }
                        }
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
    /// Selects another ticket (a blocker's id on this card).
    var select: ((String) -> Void)? = nil

    private var blocked: Bool { !ticket.waitsOn.isEmpty && ticket.column == .upNext && !ticket.yoursToDo }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(ticket.title).font(.system(size: 13, weight: .semibold)).foregroundStyle(Palette.text)
                .lineSpacing(2).multilineTextAlignment(.leading).fixedSize(horizontal: false, vertical: true)
            Text("\(ticket.id) · \(ticket.placeLine)").font(.system(size: 11)).foregroundStyle(Palette.textMuted)
            if ticket.column == .running, let stage = ticket.stage { StageBar(stage: stage) }
            if ticket.timing != nil {
                // Ticks in the app from the status's timestamps: no extra reads.
                TimelineView(.periodic(from: .now, by: ticket.column == .running ? 1 : 30)) { context in
                    if let line = ticket.timerLine(now: context.date) {
                        HStack(spacing: 4) {
                            Image(systemName: "clock").font(.system(size: 9))
                            Text(line).monospacedDigit()
                        }
                        .font(.system(size: 11))
                        .foregroundStyle(ticket.column == .needsYou ? Palette.needsYouText : Palette.textMuted)
                    }
                }
            }
            if blocked {
                // Which tickets it waits on, each one clickable.
                HStack(spacing: 4) {
                    Image(systemName: "lock").font(.system(size: 9))
                    Text("Blocked by")
                    ForEach(ticket.waitsOn, id: \.self) { id in
                        Button(id) { select?(id) }.buttonStyle(.plain).foregroundStyle(Palette.link)
                        if ticket.blockedBy?.first(where: { $0.id == id })?.handsOn == true {
                            Text("· yours").foregroundStyle(Palette.handsOnText).fixedSize()
                        }
                    }
                }
                .font(.system(size: 11)).foregroundStyle(Palette.textSoft)
            } else if let hold = ticket.hold, ticket.column == .upNext {
                // Ready, but the loop is holding it: overlapping files, or a busy Mac.
                HStack(spacing: 4) {
                    Image(systemName: "hourglass").font(.system(size: 9))
                    Text(hold.replacingOccurrences(of: "waiting: ", with: "Waiting: ")).lineLimit(2)
                }
                .font(.system(size: 11)).foregroundStyle(Palette.needsYouText)
            }
            if let blocks = ticket.blocks, !blocks.isEmpty, ticket.column != .done {
                Text("Blocks \(blocks.joined(separator: ", "))").font(.system(size: 11)).foregroundStyle(Palette.place)
            }
            HStack(spacing: 4) {
                AgentChip(agent: ticket.agent)
                RiskChip(risk: ticket.risk)
                if ticket.kind == "retro" {
                    Chip(text: "retro", foreground: Color(hex: 0xD5B3FF), background: Color(hex: 0x2D2140))
                }
                if ticket.yoursToDo {
                    Chip(text: "Hands-on · yours", foreground: Palette.handsOnText, background: Palette.handsOnFill)
                        .help("Yours to do in your own session; Runway never starts it. Mark it done when you have.")
                }
                if ticket.doneLocally == true {
                    Chip(text: "Done by hand", foreground: Palette.handsOnText, background: Palette.handsOnFill)
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
        .opacity(blocked && !selected ? 0.6 : 1)
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
    @State private var showAll = false

    var body: some View {
        // Its own scroll view, the window's height at most: a long note or review scrolls here, and never pushes the
        // toolbar or the stats strip off the window.
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                if let ticket = model.ticket {
                    content(ticket)
                } else {
                    Text("Pick a card").foregroundStyle(Palette.textMuted)
                }
            }
            .padding(18)
            .frame(maxWidth: .infinity, alignment: .topLeading)
        }
        .scrollIndicators(.automatic)
        .frame(width: 320)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(Palette.inspector)
        .onChange(of: model.selectedTicket) { note = ""; showAll = false }
    }

    @ViewBuilder private func content(_ ticket: Ticket) -> some View {
        Text("\(ticket.id) · \(ticket.column.title)").font(.system(size: 11)).foregroundStyle(Palette.textMuted)
        Text(ticket.title).font(.system(size: 16, weight: .bold)).lineSpacing(2)
            .fixedSize(horizontal: false, vertical: true)
        VStack(alignment: .leading, spacing: 6) {
            row("Filed", "\(ticket.filedFrom), \(Clock.time(ticket.filedAt))")
            row("Agent", ticket.agent.longLabel)
            if ticket.yoursToDo {
                row("Runs on", "you, by hand")
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 0) {
                    label("Runs on")
                    runsOnMenu(ticket)
                }
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
            if let blocks = ticket.blocks, !blocks.isEmpty { row("Blocks", blocks.joined(separator: ", ")) }
            if let hold = ticket.hold, ticket.column == .upNext { row("Waiting", hold.replacingOccurrences(of: "waiting: ", with: "")) }
        }
        .font(.system(size: 12))
        if ticket.heldForCapacity {
            Button { model.run(["start", ticket.id, "--ignore-capacity"]) } label: {
                Text("Start anyway").frame(maxWidth: .infinity)
            }
            .buttonStyle(PlainBoxButtonStyle())
            .help("Starts this ticket on the next tick without the memory and CPU check, this once")
        }
        if let blockers = ticket.blockedBy, !blockers.isEmpty { waitsOn(blockers) }
        if let timing = ticket.timing, timing.startedAt != nil || timing.waitingSince != nil { timeSection(ticket, timing) }
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
        Spacer(minLength: 8)
        if let runs = ticket.retroRuns, !runs.isEmpty { runsBehind(runs) }
        if let prompt = model.takePrompts[ticket.id] { takePrompt(prompt) }
        HStack(spacing: 8) {
            if !ticket.yoursToDo {
                Button { model.workOn(ticket.id) } label: {
                    Text("Work on this in Claude Code or Codex").frame(maxWidth: .infinity)
                }
                .buttonStyle(TakeBackButtonStyle())
                .help("Copies one prompt. The session talks it through, takes it back only if it changes code, and "
                      + "always tells Runway how it ended.")
            }
            if ticket.column != .running {
                Button { model.perform(.deleteTicket, ticket: ticket) } label: {
                    Image(systemName: "trash").foregroundStyle(Color(hex: 0xFF9A94))
                }
                .buttonStyle(PlainBoxButtonStyle())
                .help("Delete ticket…")
            }
        }
        if ticket.yoursToDo {
            yoursToDo(ticket)
        } else if ticket.taken == true {
            Button { model.run(["give", ticket.id]) } label: {
                Text("Give back").frame(maxWidth: .infinity)
            }
            .buttonStyle(PlainBoxButtonStyle())
            .help("Pushes your commits and queues it again; both reviews run on your commit")
        }
    }

    /// A hands-on ticket: it's the person's, so the panel says what to do and gives the prompt and Mark done.
    private func yoursToDo(_ ticket: Ticket) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            SectionHeading(text: "Yours to do", color: Palette.handsOnText)
            Text("Runway never starts this one: it needs you (a device, the simulator, how it feels). Do it in your "
                 + "own Claude Code or Codex session with the prompt, then mark it done; what waits on it starts then.")
                .font(.system(size: 12)).foregroundStyle(Palette.textSoft).fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 8) {
                Button { model.takeBack(ticket.id) } label: { Text("Copy prompt").frame(maxWidth: .infinity) }
                    .buttonStyle(PlainBoxButtonStyle())
                    .help("Makes its worktree and copies a prompt for your own session")
                Button { model.perform(.markDone, ticket: ticket) } label: { Text("Mark done").frame(maxWidth: .infinity) }
                    .buttonStyle(PrimaryButtonStyle())
                    .help("runway done \(ticket.id): finished by hand")
            }
        }
        .padding(12)
        .background(Palette.handsOnFill, in: RoundedRectangle(cornerRadius: 8))
    }

    /// When it started and how the time went: per part for a finished ticket, so far for a running one.
    private func timeSection(_ ticket: Ticket, _ t: Ticket.Timing) -> some View {
        TimelineView(.periodic(from: .now, by: 1)) { context in
            VStack(alignment: .leading, spacing: 4) {
                SectionHeading(text: "Time")
                if let line = ticket.timerLine(now: context.date) { Text(line).monospacedDigit() }
                if let start = t.startedAt { row("Started", Clock.time(start)) }
                let labels = [("build", "Build and check"), ("fix", "Fix passes"), ("review", "Reviews"),
                              ("waiting_for_you", "Waiting for you"), ("queued", "In the queue")]
                ForEach(labels, id: \.0) { key, label in
                    if let s = t.parts?[key], s > 0 { row(label, Duration.words(Double(s))) }
                }
                if let runs = t.runs, runs.count > 1 {
                    Text(runs.map { "\($0.kind == "build" ? "build" : "\($0.role ?? "code") review") \(Duration.words(Double($0.seconds)))" }
                        .joined(separator: " · "))
                        .font(.system(size: 11)).foregroundStyle(Palette.textMuted).fixedSize(horizontal: false, vertical: true)
                }
            }
            .font(.system(size: 12))
        }
    }

    /// Each ticket this one waits on, where it is, and what holds that one; with a take-back button, so the person
    /// can unblock things in their own session.
    private func waitsOn(_ blockers: [Ticket.Blocker]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            SectionHeading(text: "Waits on")
            ForEach(blockers, id: \.id) { b in
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 6) {
                        Button(b.id) { model.selectedTicket = b.id }.buttonStyle(.plain).foregroundStyle(Palette.link)
                        Text(b.title ?? "").lineLimit(1)
                        Spacer(minLength: 0)
                        Text(b.handsOn == true && b.column == .upNext ? "hands-on, yours" : b.column?.title ?? "gone")
                            .font(.system(size: 11))
                            .foregroundStyle(b.handsOn == true ? Palette.handsOnText : Palette.textMuted)
                    }
                    if !b.waitsOn.isEmpty {
                        Text("which waits on \(b.waitsOn.joined(separator: ", "))").font(.system(size: 11))
                            .foregroundStyle(Palette.textMuted)
                    }
                    if b.handsOn == true && b.column == .upNext {
                        Button("Copy \(b.id)'s prompt") { model.takeBack(b.id) }.buttonStyle(PlainBoxButtonStyle(small: true))
                    } else if b.column == .upNext || b.column == .needsYou {
                        Button("Work on \(b.id) in Claude Code or Codex") { model.workOn(b.id) }
                            .buttonStyle(PlainBoxButtonStyle(small: true))
                            .help("Copies one prompt for your own session; it takes it back only if it changes code")
                    }
                }
            }
        }
        .font(.system(size: 12))
        .padding(.horizontal, 12).padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Palette.card, in: RoundedRectangle(cornerRadius: 8))
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
                .lineLimit(showAll ? nil : 12).textSelection(.enabled)
            if question.text.count > 600 {
                Button(showAll ? "Show less" : "Show all") { showAll.toggle() }.buttonStyle(.plain)
                    .font(.system(size: 11)).foregroundStyle(Palette.link)
            }
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
