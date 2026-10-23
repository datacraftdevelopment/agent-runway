import SwiftUI
import RunwayCore

@main
struct RunwayApp: App {
    var body: some Scene {
        Window("Runway", id: "runway") { Text("Runway \(RunwayCore.version)").padding() }
    }
}
