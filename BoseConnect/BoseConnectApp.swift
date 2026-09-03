import AppKit
import SwiftUI
import Combine
import ServiceManagement

class AppDelegate: NSObject, NSApplicationDelegate {
    private var statusItem: NSStatusItem!
    private var popover: NSPopover!
    private let controller = BoseController()
    private var cancellable: AnyCancellable?

    func applicationDidFinishLaunching(_ notification: Notification) {
        if !UserDefaults.standard.bool(forKey: "launchAtLoginConfigured") {
            try? SMAppService.mainApp.register()
            UserDefaults.standard.set(true, forKey: "launchAtLoginConfigured")
        }

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        statusItem.isVisible = false

        if let button = statusItem.button {
            button.action = #selector(togglePopover)
            button.target = self
        }

        let hc = NSHostingController(rootView: ContentView().environmentObject(controller))
        hc.sizingOptions = .preferredContentSize
        popover = NSPopover()
        popover.contentViewController = hc
        popover.behavior = .transient

        cancellable = controller.objectWillChange
            .receive(on: RunLoop.main)
            .sink { [weak self] _ in
                DispatchQueue.main.async { self?.syncStatusItem() }
            }
    }

    private func syncStatusItem() {
        statusItem.isVisible = controller.isConnected
        guard let button = statusItem.button, controller.isConnected else { return }
        let cfg = NSImage.SymbolConfiguration(pointSize: 13, weight: .regular)
        button.image = NSImage(systemSymbolName: "waveform", accessibilityDescription: nil)?
            .withSymbolConfiguration(cfg)
        button.imagePosition = .imageLeft
        button.title = " \(controller.menuBarLabel)"
    }

    @objc private func togglePopover() {
        if popover.isShown {
            popover.performClose(nil)
        } else if let button = statusItem.button {
            popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
        }
    }
}

@main
struct BoseConnectApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) var appDelegate

    var body: some Scene {
        Settings { EmptyView() }
    }
}
