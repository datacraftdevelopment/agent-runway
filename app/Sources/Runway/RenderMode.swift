import AppKit
import SwiftUI

/// `RUNWAY_RENDER=<folder>`: render each screen offscreen from the current status, write PNGs and quit. For checking
/// the app when no window can be captured (a locked screen, a remote session). ImageRenderer draws neither ScrollView
/// contents (the board's cards) nor text fields, so those come out blank; everything else is the real view.
@MainActor
enum RenderMode {
    static var folder: URL? {
        ProcessInfo.processInfo.environment["RUNWAY_RENDER"].map { URL(fileURLWithPath: $0) }
    }

    static func renderAndQuit(_ model: AppModel) {
        guard let folder else { return }
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        write(MainWindow(model: model).frame(width: 1280, height: 800), "board", folder)
        model.tab = .activity
        write(MainWindow(model: model).frame(width: 1280, height: 800), "activity", folder)
        model.tab = .board
        write(SidePanel(model: model).frame(height: 640), "side-panel", folder)
        write(MenuBarContent(model: model).fixedSize(), "menu", folder)
        write(FirstRunView(model: model), "first-run", folder)
        NSApplication.shared.terminate(nil)
    }

    private static func write<V: View>(_ view: V, _ name: String, _ folder: URL) {
        let renderer = ImageRenderer(content: view.environment(\.colorScheme, .dark))
        renderer.scale = 2
        guard let image = renderer.nsImage, let tiff = image.tiffRepresentation,
              let png = NSBitmapImageRep(data: tiff)?.representation(using: .png, properties: [:]) else { return }
        try? png.write(to: folder.appendingPathComponent("\(name).png"))
    }
}
