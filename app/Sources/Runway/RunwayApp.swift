import SwiftUI
import RunwayCore

@main
struct RunwayApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        Window("Runway", id: "runway") {
            MainWindow(model: model)
                .background(LaunchOpener())
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 1280, height: 800)

        Window("Runway panel", id: "runway-panel") {
            SidePanel(model: model)
        }
        .windowStyle(.hiddenTitleBar)
        .windowResizability(.contentSize)
        .defaultSize(width: 320, height: 640)
        .defaultPosition(.topTrailing)
    }
}

/// `RUNWAY_OPEN=panel` (comma-separated) opens more windows at launch, for screenshots and for trying the app.
private struct LaunchOpener: View {
    @Environment(\.openWindow) private var openWindow

    var body: some View {
        Color.clear.frame(width: 0, height: 0).task {
            let wanted = (ProcessInfo.processInfo.environment["RUNWAY_OPEN"] ?? "").split(separator: ",")
            for id in wanted { openWindow(id: "runway-\(id)") }
        }
    }
}
