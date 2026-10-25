import SwiftUI
import RunwayCore

/// A menu bar app (no Dock icon in Runway.app) with three windows: the main window, the side panel and setup.
@main
struct RunwayApp: App {
    @State private var model = AppModel()

    init() {
        // Start Sparkle at launch, so its daily check runs whether or not the menu is ever opened.
        _ = AppUpdater.shared
    }

    // The main window comes first: it is the scene that opens at launch.
    var body: some Scene {
        Window("Runway", id: "runway") {
            MainWindow(model: model)
                .background(LaunchOpener(model: model))
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 1280, height: 800)
        .commands { WhatsNewCommand(model: model) }

        MenuBarExtra {
            MenuBarContent(model: model, dismiss: { NSApp.keyWindow?.close() })
        } label: {
            MenuBarLabel(model: model)
        }
        .menuBarExtraStyle(.window)

        Window("Runway panel", id: "runway-panel") {
            SidePanel(model: model)
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentSize)
        .defaultSize(width: 320, height: 640)
        .defaultPosition(.topTrailing)

        Window("Set up Runway", id: "runway-setup") {
            SetupGuideView(model: model)
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentSize)

        Window("What's New in Runway", id: "runway-whatsnew") {
            WhatsNewView(model: model)
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentSize)

        // The menu's content in a plain window, so it can be screenshotted and tried without clicking the menu bar.
        Window("Runway menu", id: "runway-menu") {
            MenuBarContent(model: model).fixedSize()
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentSize)
    }
}

/// `RUNWAY_OPEN=panel,menu,setup` (comma-separated) opens more windows at launch, for screenshots and trying the app.
/// It runs once, from whichever scene appears first.
private struct LaunchOpener: View {
    let model: AppModel
    @Environment(\.openWindow) private var openWindow
    @MainActor private static var done = false

    var body: some View {
        Color.clear.frame(width: 0, height: 0).task {
            guard !Self.done else { return }
            Self.done = true
            // Run from Downloads or the disk image: offer the move first, since updates only work from Applications.
            MoveToApplications.offerIfNeeded()
            let wanted = (ProcessInfo.processInfo.environment["RUNWAY_OPEN"] ?? "").split(separator: ",")
            for id in wanted { openWindow(id: "runway-\(id)") }
            if wanted.contains("whatsnew") { model.showAllNotes() }
            // Then the walkthrough (first launch, or something missing) or What's New (after an update).
            // A menu bar app isn't brought forward on its own, so the window would open behind whatever is in front.
            switch await model.launchScreen() {
            case .guide where !wanted.contains("setup"):
                NSApplication.shared.activate(ignoringOtherApps: true)
                openWindow(id: "runway-setup")
            case .whatsNew where !wanted.contains("whatsnew"):
                NSApplication.shared.activate(ignoringOtherApps: true)
                openWindow(id: "runway-whatsnew")
            default: break
            }
        }
    }
}

/// "What's New…" in the app menu, under About.
private struct WhatsNewCommand: Commands {
    let model: AppModel
    @Environment(\.openWindow) private var openWindow

    var body: some Commands {
        CommandGroup(after: .appInfo) {
            Button("What's New…") {
                model.showAllNotes()
                openWindow(id: "runway-whatsnew")
            }
        }
    }
}
