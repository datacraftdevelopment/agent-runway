// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Runway",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "Runway", targets: ["Runway"]),
        .library(name: "RunwayCore", targets: ["RunwayCore"]),
    ],
    dependencies: [
        // Updates: pinned exactly, bumped on purpose. make-app.sh copies Sparkle.framework into the app.
        .package(url: "https://github.com/sparkle-project/Sparkle", exact: "2.10.0"),
    ],
    targets: [
        // Models and status decoding. No UI, so it tests without a window.
        .target(name: "RunwayCore"),
        .executableTarget(name: "Runway", dependencies: [
            "RunwayCore",
            .product(name: "Sparkle", package: "Sparkle"),
        ]),
        .testTarget(name: "RunwayCoreTests", dependencies: ["RunwayCore"], resources: [.copy("Fixtures")]),
    ]
)
