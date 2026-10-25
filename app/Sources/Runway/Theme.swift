import SwiftUI
import RunwayCore

/// The mock's palette. The app is dark only, like the mock.
enum Palette {
    static let window = Color(hex: 0x1E1E1E)
    static let sidebar = Color(hex: 0x262628)
    static let inspector = Color(hex: 0x232325)
    static let card = Color(hex: 0x2C2C2E)
    static let control = Color(hex: 0x2C2C2E)
    static let selectedRow = Color(hex: 0x3A3A3C)
    static let segmentOn = Color(hex: 0x48484A)
    static let border = Color(hex: 0x3A3A3C)
    static let controlBorder = Color(hex: 0x48484A)
    static let code = Color(hex: 0x0F0F10)

    static let text = Color(hex: 0xF2F2F2)
    static let textSoft = Color(hex: 0xC7C7CC)
    static let textMuted = Color(hex: 0xA1A1A6)
    static let link = Color(hex: 0x4DA3FF)
    static let place = Color(hex: 0x8CC4FF)

    static let green = Color(hex: 0x30D158)
    static let blue = Color(hex: 0x0A84FF)
    static let orange = Color(hex: 0xFF9F0A)
    static let grey = Color(hex: 0x8E8E93)

    static let needsYouFill = Color(hex: 0x3A2A12)
    static let needsYouBorder = Color(hex: 0x6B4A17)
    static let needsYouText = Color(hex: 0xFFC46B)

    static let runningPillFill = Color(hex: 0x1F3A26)
    static let runningPillText = Color(hex: 0x7EE59A)
}

extension Color {
    init(hex: UInt32) {
        self.init(.sRGB, red: Double((hex >> 16) & 0xFF) / 255, green: Double((hex >> 8) & 0xFF) / 255,
                  blue: Double(hex & 0xFF) / 255, opacity: 1)
    }
}

/// Claude Code, Codex and Any each keep their own colours everywhere they appear.
extension Ticket.AgentChoice {
    var label: String {
        switch self {
        case .claude: return "Claude"
        case .codex: return "Codex"
        case .any: return "Any"
        }
    }

    var longLabel: String {
        switch self {
        case .claude: return "Claude Code"
        case .codex: return "Codex"
        case .any: return "Any (whichever is free)"
        }
    }

    var foreground: Color {
        switch self {
        case .claude: return Color(hex: 0xF0A283)
        case .codex: return Color(hex: 0x7CC0FF)
        case .any: return Color(hex: 0xD1D1D6)
        }
    }

    var background: Color {
        switch self {
        case .claude: return Color(hex: 0x3B2219)
        case .codex: return Color(hex: 0x12304D)
        case .any: return Color(hex: 0x3A3A3C)
        }
    }

    /// The small square in the sidebar's agent list.
    var swatch: Color {
        switch self {
        case .claude: return Color(hex: 0xD97757)
        case .codex: return Color(hex: 0x3A96F5)
        case .any: return Palette.grey
        }
    }
}

extension AgentKind {
    var choice: Ticket.AgentChoice { self == .claude ? .claude : .codex }
    var name: String { self == .claude ? "Claude Code" : "Codex" }
}

extension Ticket.Risk {
    var label: String { self == .low ? "low" : "not low" }
    var longLabel: String { self == .low ? "Low: can merge on its own" : "Not low: waits for you" }
    var foreground: Color { self == .low ? Color(hex: 0x7EE59A) : Color(hex: 0xFF9FBF) }
    var background: Color { self == .low ? Color(hex: 0x1F3A26) : Color(hex: 0x45202D) }
}

extension Ticket.Column {
    var title: String {
        switch self {
        case .needsYou: return "Needs you"
        case .upNext: return "Up next"
        case .running: return "Running"
        case .done: return "Done"
        }
    }

    var dot: Color {
        switch self {
        case .needsYou: return Palette.orange
        case .upNext: return Palette.grey
        case .running: return Palette.blue
        case .done: return Palette.green
        }
    }
}

extension Ticket.Stage {
    var label: String { rawValue.capitalized }
    /// "reviewing", for the side panel's one-line summary.
    var doing: String {
        switch self {
        case .build: return "building"
        case .check: return "checking"
        case .review: return "reviewing"
        case .merge: return "merging"
        }
    }
}

extension Repo.State {
    var dot: Color {
        switch self {
        case .running: return Palette.green
        case .idle, .off: return Palette.grey
        case .needsYou, .paused: return Palette.orange
        }
    }
}

extension Runner.State {
    var dot: Color { self == .online ? Palette.green : Palette.grey }
}

extension ActivityLine.Kind {
    var label: String { self == .needsYou ? "needs you" : rawValue }
    var colors: (fill: Color, text: Color) {
        switch self {
        case .filed: return (Color(hex: 0x2F2F45), Color(hex: 0xC9C9FF))
        case .start: return (Color(hex: 0x13304F), Color(hex: 0x8CC4FF))
        case .review: return (Color(hex: 0x3A2350), Color(hex: 0xE0B3FF))
        case .merged: return (Color(hex: 0x1F3A26), Color(hex: 0x7EE59A))
        case .needsYou: return (Palette.needsYouFill, Palette.needsYouText)
        case .limit, .failed: return (Color(hex: 0x4A1F1F), Color(hex: 0xFF9A94))
        case .answer: return (Color(hex: 0x13304F), Color(hex: 0x8CC4FF))
        case .setup, .other: return (Palette.selectedRow, Palette.textSoft)
        }
    }
}

extension SetupRow.Check {
    var label: String {
        switch self {
        case .yes: return "yes"
        case .checking: return "checking"
        case .signIn: return "sign in"
        case .no: return "no"
        case .optional: return "optional"
        }
    }

    var color: Color {
        switch self {
        case .yes: return Color(hex: 0x7EE59A)
        case .checking: return Color(hex: 0x8CC4FF)
        case .signIn, .no: return Color(hex: 0xFFC46B)
        case .optional: return Palette.textMuted
        }
    }
}

// MARK: Pieces

struct Dot: View {
    let color: Color
    var size: CGFloat = 8

    var body: some View { Circle().fill(color).frame(width: size, height: size) }
}

struct Chip: View {
    let text: String
    let foreground: Color
    let background: Color

    var body: some View {
        Text(text).font(.system(size: 11)).foregroundStyle(foreground)
            .padding(.horizontal, 7).padding(.vertical, 2)
            .background(background, in: Capsule())
    }
}

struct AgentChip: View {
    let agent: Ticket.AgentChoice
    var body: some View { Chip(text: agent.label, foreground: agent.foreground, background: agent.background) }
}

struct RiskChip: View {
    let risk: Ticket.Risk
    var body: some View { Chip(text: risk.label, foreground: risk.foreground, background: risk.background) }
}

/// Build, Check, Review, Merge: done stages green, the current one blue and bold, later ones grey.
struct StageBar: View {
    let stage: Ticket.Stage

    var body: some View {
        let current = Ticket.Stage.allCases.firstIndex(of: stage) ?? 0
        HStack(spacing: 3) {
            ForEach(Array(Ticket.Stage.allCases.enumerated()), id: \.offset) { index, step in
                VStack(alignment: .leading, spacing: 4) {
                    Capsule().fill(fill(index, current)).frame(height: 4)
                    Text(step.label).font(.system(size: 10, weight: index == current ? .bold : .regular))
                        .foregroundStyle(labelColor(index, current)).lineLimit(1).fixedSize()
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private func fill(_ index: Int, _ current: Int) -> Color {
        index < current ? Palette.green : index == current ? Palette.blue : Palette.segmentOn
    }

    private func labelColor(_ index: Int, _ current: Int) -> Color {
        index < current ? Color(hex: 0x7EE59A) : index == current ? Palette.place : Palette.grey
    }
}

/// The small tracking-wide caps heading: "REPOS", "NEEDS YOU · 2".
struct SectionHeading: View {
    let text: String
    var color: Color = Palette.textMuted

    var body: some View {
        Text(text.uppercased()).font(.system(size: 11, weight: .bold)).tracking(0.5).foregroundStyle(color)
    }
}

/// A two-option segmented control in the mock's style (Board/Activity, Claude Code/Codex).
struct Segmented<Value: Hashable>: View {
    let options: [(Value, String)]
    @Binding var selection: Value
    var stretch = false

    var body: some View {
        HStack(spacing: 0) {
            ForEach(options, id: \.0) { value, title in
                Button { selection = value } label: {
                    Text(title).font(.system(size: 12)).foregroundStyle(Palette.text)
                        .padding(.horizontal, stretch ? 5 : 14).padding(.vertical, 5)
                        .frame(maxWidth: stretch ? .infinity : nil)
                        .background(selection == value ? Palette.segmentOn : .clear, in: RoundedRectangle(cornerRadius: 5))
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
        }
        .padding(2)
        .background(stretch ? Palette.window : Palette.control, in: RoundedRectangle(cornerRadius: 7))
    }
}

/// The mock's bordered grey button.
struct PlainBoxButtonStyle: ButtonStyle {
    var fill: Color = Palette.control
    var small = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.system(size: small ? 12 : 13)).foregroundStyle(Palette.text)
            .padding(.horizontal, small ? 10 : 12).padding(.vertical, small ? 4 : 6)
            .background(fill.opacity(configuration.isPressed ? 0.7 : 1), in: RoundedRectangle(cornerRadius: 6))
            .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Palette.controlBorder))
    }
}

/// The mock's amber Take back button.
struct TakeBackButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.system(size: 13, weight: .semibold)).foregroundStyle(Palette.needsYouText)
            .padding(.horizontal, 12).padding(.vertical, 8)
            .background(Palette.needsYouFill.opacity(configuration.isPressed ? 0.7 : 1), in: RoundedRectangle(cornerRadius: 6))
            .overlay(RoundedRectangle(cornerRadius: 6).strokeBorder(Color(hex: 0xB07A2A)))
    }
}

/// The mock's filled blue button.
struct PrimaryButtonStyle: ButtonStyle {
    var small = false

    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.system(size: small ? 12 : 13, weight: small ? .regular : .semibold))
            .foregroundStyle(.white)
            .padding(.horizontal, small ? 10 : 12).padding(.vertical, small ? 4 : 8)
            .background(Palette.blue.opacity(configuration.isPressed ? 0.7 : 1), in: RoundedRectangle(cornerRadius: 6))
    }
}

enum Clock {
    static func time(_ date: Date) -> String {
        let formatter = DateFormatter()
        formatter.dateFormat = "HH:mm"
        return formatter.string(from: date)
    }

    /// 850 → "14:10".
    static func elapsed(_ seconds: Int) -> String {
        String(format: "%d:%02d", seconds / 60, seconds % 60)
    }
}

#Preview("Chips and stage bar") {
    VStack(alignment: .leading, spacing: 12) {
        HStack { AgentChip(agent: .claude); AgentChip(agent: .codex); AgentChip(agent: .any) }
        HStack { RiskChip(risk: .low); RiskChip(risk: .notLow) }
        StageBar(stage: .build)
        StageBar(stage: .review)
    }
    .padding().frame(width: 280).background(Palette.card)
}
