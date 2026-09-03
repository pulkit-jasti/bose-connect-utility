import SwiftUI

@main
struct BoseConnectApp: App {
    @StateObject private var controller = BoseController()

    var body: some Scene {
        MenuBarExtra {
            ContentView()
                .environmentObject(controller)
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "waveform")
                Text(controller.menuBarLabel)
                    .font(.system(size: 12))
            }
        }
        .menuBarExtraStyle(.window)
    }
}
