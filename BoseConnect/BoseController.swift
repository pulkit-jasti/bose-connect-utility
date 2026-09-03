import Foundation
import IOBluetooth

class BoseController: NSObject, ObservableObject, IOBluetoothRFCOMMChannelDelegate {
    @Published var battery: Int?
    @Published var isConnected = false
    @Published var deviceName = "No Bose device"
    @Published var lastANC: String?

    var menuBarLabel: String {
        guard isConnected else { return "--" }
        let batt = battery.map { "\($0)%" } ?? "..."
        guard let anc = lastANC else { return batt }
        let names = ["high": "High", "low": "Low", "off": "Off"]
        return "\(batt) · \(names[anc] ?? anc)"
    }

    private let CHANNEL: BluetoothRFCOMMChannelID = 9
    private let HANDSHAKE: [UInt8] = [0x00, 0x01, 0x01, 0x00]
    private let BATT_GET:  [UInt8] = [0x02, 0x02, 0x01, 0x00]
    private let ANC_CMDS:  [String: [UInt8]] = [
        "high": [0x01, 0x06, 0x02, 0x01, 0x01],
        "low":  [0x01, 0x06, 0x02, 0x01, 0x03],
        "off":  [0x01, 0x06, 0x02, 0x01, 0x00],
    ]

    private var device: IOBluetoothDevice?
    private var pendingANC: [UInt8]?

    override init() {
        super.init()
        refresh()
        Timer.scheduledTimer(withTimeInterval: 30, repeats: true) { [weak self] _ in self?.refresh() }
    }

    func refresh() {
        findDevice()
        guard device?.isConnected() == true else {
            DispatchQueue.main.async { self.battery = nil }
            return
        }
        openChannel(anc: nil)
    }

    func setANC(_ level: String) {
        guard let cmd = ANC_CMDS[level] else { return }
        DispatchQueue.main.async { self.lastANC = level }
        openChannel(anc: cmd)
    }

    // MARK: - Private

    private func findDevice() {
        let paired = IOBluetoothDevice.pairedDevices() as? [IOBluetoothDevice] ?? []
        device = paired.first {
            let n = $0.name?.lowercased() ?? ""
            return n.contains("bose") || n.contains("qc") || n.contains("quietcomfort") ||
                   n.contains("soundsport") || n.contains("soundlink")
        }
        DispatchQueue.main.async {
            self.isConnected  = self.device?.isConnected() == true
            self.deviceName   = self.device?.name ?? "No Bose device"
        }
    }

    private func openChannel(anc: [UInt8]?) {
        guard let device else { return }
        pendingANC = anc
        var ch: IOBluetoothRFCOMMChannel?
        device.openRFCOMMChannelAsync(&ch, withChannelID: CHANNEL, delegate: self)
    }

    // MARK: - IOBluetoothRFCOMMChannelDelegate

    func rfcommChannelOpenComplete(_ ch: IOBluetoothRFCOMMChannel!, status err: IOReturn) {
        guard err == 0 else { return }
        var buf = HANDSHAKE + (pendingANC ?? []) + BATT_GET
        ch.writeSync(&buf, length: UInt16(buf.count))
        DispatchQueue.main.asyncAfter(deadline: .now() + 3) { ch.close() }
    }

    func rfcommChannelData(_ ch: IOBluetoothRFCOMMChannel!,
                           data ptr: UnsafeMutableRawPointer!, length n: Int) {
        guard let ptr, n > 0 else { return }
        let bytes = Array(UnsafeBufferPointer(start: ptr.assumingMemoryBound(to: UInt8.self), count: n))
        var i = 0
        while i + 4 < bytes.count {
            if bytes[i] == 0x02, bytes[i+1] == 0x02, bytes[i+2] == 0x03 {
                let pct = Int(bytes[i+4])
                DispatchQueue.main.async { self.battery = pct }
                ch.close()
                return
            }
            i += 1
        }
    }

    func rfcommChannelClosed(_ ch: IOBluetoothRFCOMMChannel!) {}
}
