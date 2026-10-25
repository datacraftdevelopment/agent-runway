// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "Runway",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "Runway", targets: ["Runway"]),
        .library(name: "RunwayCore", targets: ["RunwayCore"]),
    ],
    targets: [
        // Models and status decoding. No UI, so it tests without a window.
        .target(name: "RunwayCore"),
        .executableTarget(name: "Runway", dependencies: ["RunwayCore"]),
        .testTarget(name: "RunwayCoreTests", dependencies: ["RunwayCore"], resources: [.copy("Fixtures")]),
    ]
)
