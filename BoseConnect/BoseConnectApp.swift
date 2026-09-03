import SwiftUI

@main
struct BoseConnectApp: App {
    @StateObject private var controller = BoseController()

    var body: some Scene {
        MenuBarExtra {
            ContentView()
                .environmentObject(controller)
        } label: {
            Label(controller.menuBarLabel, systemImage: "headphones")
        }
        .menuBarExtraStyle(.menu)
    }
}
