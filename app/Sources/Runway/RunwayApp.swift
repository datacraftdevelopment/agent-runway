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
                .background(LaunchOpener())
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 1280, height: 800)

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
            FirstRunView(model: model)
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
    @Environment(\.openWindow) private var openWindow
    @MainActor private static var done = false

    var body: some View {
        Color.clear.frame(width: 0, height: 0).task {
            guard !Self.done else { return }
            Self.done = true
            let wanted = (ProcessInfo.processInfo.environment["RUNWAY_OPEN"] ?? "").split(separator: ",")
            for id in wanted { openWindow(id: "runway-\(id)") }
        }
    }
}
