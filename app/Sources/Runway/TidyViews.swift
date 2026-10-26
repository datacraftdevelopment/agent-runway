import SwiftUI
import RunwayCore

/// A context menu from RunwayCore's ContextMenus: submenus, dividers, a check on the current choice, red for deletes.
struct MenuItemsView: View {
    let items: [MenuItem]
    let perform: (MenuAction) -> Void

    var body: some View {
        ForEach(Array(items.enumerated()), id: \.offset) { _, item in
            if item.isDivider {
                Divider()
            } else if !item.children.isEmpty {
                Menu(item.title) { MenuItemsView(items: item.children, perform: perform) }
            } else if let action = item.action {
                Button(role: item.destructive ? .destructive : nil) { perform(action) } label: {
                    if item.checked { Label(item.title, systemImage: "checkmark") } else { Text(item.title) }
                }
            }
        }
    }
}

/// The note at the bottom of the main window, with Undo when the step can be undone.
struct ToastView: View {
    let toast: Toast
    let model: AppModel

    var body: some View {
        HStack(spacing: 14) {
            Text(toast.text).foregroundStyle(toast.error ? Color(hex: 0xFF9A94) : Palette.text).lineLimit(2)
            if toast.undo != nil {
                Button("Undo") { model.undo(toast) }.buttonStyle(.plain).foregroundStyle(Palette.link)
                    .font(.system(size: 13, weight: .semibold))
            }
            Button { model.toast = nil } label: { Image(systemName: "xmark").font(.system(size: 10, weight: .bold)) }
                .buttonStyle(.plain).foregroundStyle(Palette.textMuted)
        }
        .font(.system(size: 13))
        .padding(.horizontal, 16).padding(.vertical, 10)
        .background(Palette.selectedRow, in: Capsule())
        .overlay(Capsule().strokeBorder(Palette.controlBorder))
        .shadow(color: .black.opacity(0.4), radius: 12, y: 4)
    }
}

/// The confirm sheet for a step that deletes: exactly what goes, and what stays.
struct ConfirmSheet: View {
    let confirm: Confirm
    let model: AppModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text(confirm.title).font(.system(size: 17, weight: .bold))
            list("Deleted for good", confirm.goes, mark: "✗", color: Color(hex: 0xFF9A94))
            list("Left as it is", confirm.stays, mark: "✓", color: Palette.green)
            HStack {
                Spacer()
                Button("Cancel") { model.confirm = nil; dismiss() }.buttonStyle(PlainBoxButtonStyle())
                    .keyboardShortcut(.cancelAction)
                Button(confirm.button) { model.confirmed(confirm); dismiss() }
                    .buttonStyle(DestructiveButtonStyle())
            }
        }
        .font(.system(size: 13))
        .foregroundStyle(Palette.text)
        .padding(24)
        .frame(width: 440)
        .background(Palette.window)
        .preferredColorScheme(.dark)
    }

    private func list(_ heading: String, _ lines: [String], mark: String, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            SectionHeading(text: heading)
            ForEach(lines, id: \.self) { line in
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(mark).foregroundStyle(color)
                    Text(line).fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

/// The red button on a confirm sheet.
struct DestructiveButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label.font(.system(size: 13, weight: .semibold)).foregroundStyle(.white)
            .padding(.horizontal, 14).padding(.vertical, 7)
            .background(Color(hex: 0xD93A33).opacity(configuration.isPressed ? 0.7 : 1),
                        in: RoundedRectangle(cornerRadius: 6))
    }
}

/// "Archived (n)" under the repo list: each archived repo with Unarchive, and a right-click to remove it.
struct ArchivedSection: View {
    let model: AppModel
    let archived: [ArchivedRepo]
    @State private var open = RenderMode.folder != nil

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Button { open.toggle() } label: {
                HStack(spacing: 6) {
                    Image(systemName: open ? "chevron.down" : "chevron.right").font(.system(size: 9, weight: .bold))
                    Text("Archived (\(archived.count))")
                }
                .font(.system(size: 12)).foregroundStyle(Palette.textMuted)
                .padding(.horizontal, 8).padding(.vertical, 5).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            if open {
                ForEach(archived) { repo in
                    HStack(spacing: 8) {
                        VStack(alignment: .leading, spacing: 1) {
                            Text(repo.name).foregroundStyle(Palette.textSoft)
                            Text("\(repo.tickets) ticket\(repo.tickets == 1 ? "" : "s")").font(.system(size: 11))
                                .foregroundStyle(Palette.textMuted)
                        }
                        Spacer(minLength: 0)
                        Button("Unarchive") { model.perform(.unarchive, repo: repo.name) }
                            .buttonStyle(PlainBoxButtonStyle(small: true))
                    }
                    .padding(.horizontal, 8).padding(.vertical, 4)
                    .contentShape(Rectangle())
                    .contextMenu {
                        MenuItemsView(items: ContextMenus.archived(repo)) { model.perform($0, repo: repo.name) }
                    }
                }
            }
        }
    }
}
