import SwiftUI

struct ContentView: View {
    @EnvironmentObject var controller: BoseController

    var body: some View {
        Text(controller.isConnected
             ? "\(controller.deviceName)  ·  \(controller.battery.map { "\($0)%" } ?? "...")"
             : "Not connected")
            .foregroundStyle(.secondary)

        Divider()

        Button(ancLabel("high")) { controller.setANC("high") }
        Button(ancLabel("low"))  { controller.setANC("low") }
        Button(ancLabel("off"))  { controller.setANC("off") }

        Divider()

        Button("Refresh") { controller.refresh() }

        Divider()

        Button("Quit") { NSApplication.shared.terminate(nil) }
    }

    private func ancLabel(_ level: String) -> String {
        let names = ["high": "High", "low": "Low", "off": "Off"]
        let mark  = controller.lastANC == level ? "✓ " : "   "
        return "\(mark)ANC: \(names[level] ?? level)"
    }
}
