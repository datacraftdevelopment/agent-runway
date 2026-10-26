import Foundation

/// What right-clicking a ticket, a repo, an archived repo or a runner offers, by its state. Data only, so it tests
/// without a window: the app turns each action into a `runway` command (or a copy, a link, a reveal).
public enum MenuAction: Equatable, Sendable {
    // Tickets
    case discussTicket, takeBack, copyTakePrompt, giveBack, go, no, openPR, copyTicketID, ticketRunsOn(String?)
    case deleteTicket
    // Repos
    case discussRepo, pauseRepo, resumeRepo, repoRunsOn(Repo.RunsOn), mainComputer(String), openGitHub, revealFolder
    case clearDone, archive, unarchive, removeRepo, setCheck
    // Runners
    case pauseRunner, resumeRunner, maxSessions(Int)
}

public struct MenuItem: Equatable, Sendable {
    public var title: String
    public var action: MenuAction?
    public var children: [MenuItem]
    /// Shown with a check mark: the current choice in a submenu.
    public var checked: Bool
    public var destructive: Bool
    public var isDivider: Bool { title.isEmpty && action == nil && children.isEmpty }

    public static let divider = MenuItem(title: "", action: nil, children: [], checked: false, destructive: false)

    static func item(_ title: String, _ action: MenuAction, checked: Bool = false, destructive: Bool = false) -> MenuItem {
        MenuItem(title: title, action: action, children: [], checked: checked, destructive: destructive)
    }

    static func submenu(_ title: String, _ children: [MenuItem]) -> MenuItem {
        MenuItem(title: title, action: nil, children: children, checked: false, destructive: false)
    }
}

public enum ContextMenus {
    public static func ticket(_ t: Ticket, runners: [Runner]) -> [MenuItem] {
        var items: [MenuItem] = [.item("Chat about this ticket…", .discussTicket)]
        if t.column != .done {
            if t.taken == true {
                items += [.item("Copy take-back prompt again", .copyTakePrompt), .item("Give back", .giveBack)]
            } else {
                items.append(.item("Take back · copy prompt", .takeBack))
            }
        }
        if t.column == .needsYou, t.taken != true, let q = t.question {
            items += [.divider, .item(q.goLabel, .go), .item(q.noLabel, .no)]
        }
        items.append(.divider)
        if t.prUrl != nil { items.append(.item("Open PR", .openPR)) }
        items.append(.item("Copy ticket id (\(t.id))", .copyTicketID))
        if t.column == .upNext || t.column == .needsYou {
            items.append(.submenu("Runs on", [.item("Any free runner", .ticketRunsOn(nil), checked: t.runsOn == nil)]
                + runners.map { .item($0.name, .ticketRunsOn($0.name), checked: t.runsOn == $0.name) }))
        }
        if t.column != .running {
            items += [.divider, .item("Delete ticket…", .deleteTicket, destructive: true)]
        }
        return items
    }

    public static func repo(_ r: Repo, runners: [Runner], hasDone: Bool) -> [MenuItem] {
        var items: [MenuItem] = [.item("Chat about this repo…", .discussRepo), .divider]
        items.append(r.state == .paused ? .item("Resume", .resumeRepo) : .item("Pause", .pauseRepo))
        items.append(.submenu("Runs on", [
            .item("Any runner", .repoRunsOn(.any), checked: r.runsOn == .any),
            .item("Main computer only (\(r.mainComputer))", .repoRunsOn(.main), checked: r.runsOn == .main),
        ]))
        items.append(.submenu("Main computer", runners.filter { $0.kind != .cloud }.map {
            .item($0.name, .mainComputer($0.name), checked: r.mainComputer == $0.name)
        }))
        if r.slug != nil || r.path != nil { items.append(.divider) }
        if r.slug != nil { items.append(.item("Open on GitHub", .openGitHub)) }
        if r.path != nil { items.append(.item("Reveal folder in Finder", .revealFolder)) }
        items.append(.divider)
        items.append(.item(r.checkCmd == nil ? "Set check command…" : "Check command…", .setCheck))
        if hasDone { items.append(.item("Clear done", .clearDone)) }
        items += [.item("Archive", .archive), .item("Remove…", .removeRepo, destructive: true)]
        return items
    }

    public static func archived(_ a: ArchivedRepo) -> [MenuItem] {
        [.item("Unarchive", .unarchive), .divider, .item("Remove…", .removeRepo, destructive: true)]
    }

    public static func runner(_ r: Runner) -> [MenuItem] {
        [r.pausedUntil != nil ? .item("Resume \(r.name)", .resumeRunner) : .item("Pause \(r.name)", .pauseRunner),
         .submenu("Max sessions", (1...8).map { .item("\($0)", .maxSessions($0), checked: r.slotsTotal == $0) })]
    }
}
