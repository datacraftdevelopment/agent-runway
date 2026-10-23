import SwiftUI
import RunwayCore

@main
struct RunwayApp: App {
    @State private var model = AppModel()

    var body: some Scene {
        Window("Runway", id: "runway") {
            MainWindow(model: model)
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 1280, height: 800)
    }
}
