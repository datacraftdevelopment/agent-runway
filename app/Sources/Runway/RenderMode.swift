import AppKit
import SwiftUI
import RunwayCore

/// `RUNWAY_RENDER=<folder>`: render each screen offscreen from the current status, write PNGs and quit. For checking
/// the app when no window can be captured (a locked screen, a remote session). ImageRenderer draws neither ScrollView
/// contents (the board's cards) nor text fields, so those come out blank; everything else is the real view.
@MainActor
enum RenderMode {
    static var folder: URL? {
        ProcessInfo.processInfo.environment["RUNWAY_RENDER"].map { URL(fileURLWithPath: $0) }
    }

    static func renderAndQuit(_ model: AppModel) async {
        guard let folder else { return }
        // The walkthrough shows the doctor report, so wait for it (live only).
        if model.source == .live && model.setup == nil { await model.checkMac() }
        try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let start = model.guideStep
        for step in SetupGuide.Step.allCases {
            model.guideStep = step
            write(SetupGuideView(model: model), "guide-\(step.rawValue + 1)-\(step)", folder)
        }
        // RUNWAY_RENDER_SETUP=1 presses "Set it up" for real (in whatever HOME this runs with), then draws the
        // install step after it and the Next step with the result.
        if ProcessInfo.processInfo.environment["RUNWAY_RENDER_SETUP"] != nil {
            await model.setUp()
            model.guideStep = .install
            write(SetupGuideView(model: model), "guide-3-install-done", folder)
            model.guideStep = .next
            write(SetupGuideView(model: model), "guide-4-next-after", folder)
        }
        model.guideStep = start
        model.showAllNotes()
        write(WhatsNewView(model: model), "whats-new", folder)
        write(MainWindow(model: model).frame(width: 1280, height: 800), "board", folder)
        if model.source == .live && !model.firstLaunch { await model.refreshStats() }   // stats would make ~/.runway
        model.tab = .activity
        write(MainWindow(model: model).frame(width: 1280, height: 800), "activity", folder)
        model.tab = .stats
        write(MainWindow(model: model).frame(width: 1280, height: 800), "stats", folder)
        model.tab = .board
        write(SidePanel(model: model).frame(height: 640), "side-panel", folder)
        write(MenuBarContent(model: model).fixedSize(), "menu", folder)
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
