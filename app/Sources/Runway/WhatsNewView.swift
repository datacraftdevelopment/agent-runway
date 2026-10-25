import SwiftUI
import RunwayCore

/// What's New: each version since the one the person last saw, newest first, from app/release-notes. A big release
/// gets its fuller recap as numbered steps, in the walkthrough's style.
struct WhatsNewView: View {
    let model: AppModel
    @Environment(\.dismissWindow) private var dismissWindow

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 4) {
                Text("What's new in Runway").font(.system(size: 22, weight: .bold))
                Text("Version \(model.appVersion)").foregroundStyle(Palette.textMuted)
            }
            // ImageRenderer draws no ScrollView contents, so a render lays the notes out flat.
            if RenderMode.folder == nil {
                ScrollView { notes }.scrollIndicators(.automatic)
            } else {
                notes
            }
            HStack {
                Spacer()
                Button("Got it") { dismissWindow(id: "runway-whatsnew") }.buttonStyle(PrimaryButtonStyle())
            }
        }
        .font(.system(size: 13))
        .foregroundStyle(Palette.text)
        .padding(.horizontal, 30).padding(.top, 34).padding(.bottom, 24)
        .frame(width: 640, alignment: .topLeading)
        .frame(minHeight: 300, maxHeight: 640, alignment: .topLeading)
        .background(Palette.window)
        .ignoresSafeArea()
        .preferredColorScheme(.dark)
    }

    private var notes: some View {
        VStack(alignment: .leading, spacing: 22) {
            if model.whatsNew.isEmpty {
                Text("No release notes in this build.").foregroundStyle(Palette.textMuted)
            }
            ForEach(model.whatsNew, id: \.version.description) { note in
                VStack(alignment: .leading, spacing: 10) {
                    SectionHeading(text: "Runway \(note.version)" + (note.big ? " · a big one" : ""),
                                   color: note.big ? Palette.place : Palette.textMuted)
                    ForEach(Array(note.lines.enumerated()), id: \.offset) { _, line in bullet(line) }
                    if !note.sections.isEmpty {
                        LazyVGrid(columns: [GridItem(.flexible(), spacing: 12, alignment: .top),
                                            GridItem(.flexible(), spacing: 12, alignment: .top)],
                                  alignment: .leading, spacing: 12) {
                            ForEach(Array(note.sections.enumerated()), id: \.offset) { i, section in
                                step(i + 1, section)
                            }
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func step(_ number: Int, _ section: ReleaseNote.Section) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 8) {
                Text("\(number)").font(.system(size: 11, weight: .bold)).frame(width: 18, height: 18)
                    .background(Palette.blue, in: Circle()).foregroundStyle(.white)
                Text(section.title).font(.system(size: 13, weight: .semibold))
            }
            ForEach(Array(section.lines.enumerated()), id: \.offset) { _, line in
                Text(line).font(.system(size: 12)).foregroundStyle(Palette.textSoft)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, minHeight: 120, alignment: .topLeading)
        .background(Palette.card, in: RoundedRectangle(cornerRadius: 10))
    }

    private func bullet(_ text: String) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text("•").foregroundStyle(Palette.textMuted)
            Text(LocalizedStringKey(text)).fixedSize(horizontal: false, vertical: true)
        }
    }
}
