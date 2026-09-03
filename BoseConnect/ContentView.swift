import SwiftUI
import ServiceManagement

struct ContentView: View {
    @EnvironmentObject var controller: BoseController
    @State private var launchAtLogin = (SMAppService.mainApp.status == .enabled)

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(controller.isConnected ? controller.deviceName : "Not connected")
                .font(.headline)
            if controller.isConnected {
                Text(controller.battery.map { "Battery: \($0)%" } ?? "Fetching battery...")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }

            if controller.isConnected {
                Divider()

                VStack(alignment: .leading, spacing: 6) {
                    Text("Noise Cancellation")
                        .font(.caption)
                        .foregroundStyle(.secondary)

                    Picker("ANC", selection: Binding(
                        get: { controller.lastANC ?? "high" },
                        set: { controller.setANC($0) }
                    )) {
                        Text("High").tag("high")
                        Text("Low").tag("low")
                        Text("Off").tag("off")
                    }
                    .pickerStyle(.segmented)
                }
            }

            Divider()

            Toggle("Launch at Login", isOn: $launchAtLogin)
                .font(.subheadline)
                .onChange(of: launchAtLogin) { enabled in
                    do {
                        if enabled {
                            try SMAppService.mainApp.register()
                        } else {
                            try SMAppService.mainApp.unregister()
                        }
                    } catch {
                        launchAtLogin = !enabled
                    }
                }

            Divider()

            HStack {
                Button("Refresh") { controller.refresh() }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                Spacer()
                Button("Quit") { NSApplication.shared.terminate(nil) }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
            }
            .font(.subheadline)
        }
        .padding(16)
        .frame(width: 260)
    }
}
