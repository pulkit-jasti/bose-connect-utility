#!/usr/bin/env swift
import Foundation
import IOBluetooth

// ── Config ────────────────────────────────────────────────────────────────────

let CHANNEL:   BluetoothRFCOMMChannelID = 9
let HANDSHAKE: [UInt8] = [0x00, 0x01, 0x01, 0x00]
let BATT_GET:  [UInt8] = [0x02, 0x02, 0x01, 0x00]
let ANC_GET:   [UInt8] = [0x01, 0x06, 0x01, 0x03]
let ANC_SET:   [String: (bytes: [UInt8], level: UInt8)] = [
    "high": (bytes: [0x01, 0x06, 0x02, 0x01, 0x01], level: 0x01),
    "low":  (bytes: [0x01, 0x06, 0x02, 0x01, 0x03], level: 0x03),
    "off":  (bytes: [0x01, 0x06, 0x02, 0x01, 0x00], level: 0x00),
]
let ANC_NAMES: [UInt8: String] = [0x00: "Off", 0x01: "High", 0x03: "Low"]

// ── Device discovery ──────────────────────────────────────────────────────────

func isBose(_ d: IOBluetoothDevice) -> Bool {
    let n = d.name?.lowercased() ?? ""
    return n.contains("bose") || n.contains("qc") || n.contains("quietcomfort") ||
           n.contains("soundsport") || n.contains("soundlink") || n.contains("sport")
}

guard let device = (IOBluetoothDevice.pairedDevices() as? [IOBluetoothDevice])?.first(where: isBose) else {
    let all = (IOBluetoothDevice.pairedDevices() as? [IOBluetoothDevice])?.map { $0.name ?? "?" } ?? []
    print("No Bose device found. Paired devices: \(all)"); exit(1)
}

print("Device  : \(device.name ?? "?")")
print("Address : \(device.addressString ?? "?")")
print("Status  : \(device.isConnected() ? "connected" : "not connected")")

guard device.isConnected() else { exit(0) }

// ── Command parsing ───────────────────────────────────────────────────────────

enum Command {
    case status
    case ancSet(bytes: [UInt8], label: String, expectedLevel: UInt8)
    case monitor
}

let args = CommandLine.arguments.dropFirst()
let command: Command

if args.count >= 2, args[args.startIndex] == "anc" {
    let level = String(args[args.index(after: args.startIndex)])
    guard let anc = ANC_SET[level] else {
        print("Usage: swift bose.swift [status | anc high | anc low | anc off | monitor]"); exit(1)
    }
    command = .ancSet(bytes: anc.bytes, label: level, expectedLevel: anc.level)
} else if args.first == "monitor" {
    command = .monitor
} else {
    command = .status
}

// ── Session ───────────────────────────────────────────────────────────────────

class Session: NSObject, IOBluetoothRFCOMMChannelDelegate {
    let command: Command
    var gotBattery = false
    var gotANC     = false

    init(_ command: Command) { self.command = command }

    func rfcommChannelOpenComplete(_ ch: IOBluetoothRFCOMMChannel!, status err: IOReturn) {
        guard err == 0 else { print("Open failed (\(err))"); exit(1) }

        switch command {
        case .ancSet(let setBytes, _, _):
            // GadgetBridge bundles handshake + ANC SET + battery in one write
            send(ch, HANDSHAKE + setBytes + BATT_GET)
        case .status:
            send(ch, HANDSHAKE + BATT_GET + ANC_GET)
        case .monitor:
            send(ch, HANDSHAKE)
        }

        switch command {
        case .monitor:
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
                print("Monitoring — press the ANC button on your headphones (Ctrl-C to stop)")
            }
        default:
            DispatchQueue.main.asyncAfter(deadline: .now() + 4.0) { exit(0) }
        }
    }

    func rfcommChannelData(_ ch: IOBluetoothRFCOMMChannel!,
                           data ptr: UnsafeMutableRawPointer!, length n: Int) {
        guard let ptr, n > 0 else { return }
        let bytes = Array(UnsafeBufferPointer(start: ptr.assumingMemoryBound(to: UInt8.self), count: n))

        var i = 0
        while i + 4 < bytes.count {
            // Battery: 02 02 03 [len] [pct]
            if bytes[i] == 0x02, bytes[i+1] == 0x02, bytes[i+2] == 0x03 {
                print("Battery : \(bytes[i+4])%")
                gotBattery = true
                i += 4 + Int(bytes[i+3]); continue
            }
            // ANC push/confirm: 01 06 03 02 [level] 0b  (button press or SET confirmation)
            if bytes[i] == 0x01, bytes[i+1] == 0x06, bytes[i+2] == 0x03 {
                let level = bytes[i+4]
                switch command {
                case .status:
                    print("ANC     : \(ANC_NAMES[level] ?? "Unknown (0x\(String(format: "%02x", level)))")")
                case .ancSet(_, let label, let expected):
                    guard level == expected else { i += 4 + Int(bytes[i+3]); continue }
                    print("ANC     → \(label.capitalized)")
                case .monitor:
                    break
                }
                gotANC = true
                i += 4 + Int(bytes[i+3]); continue
            }
            i += 1
        }

        let done = switch command {
            case .status:   gotBattery && gotANC
            case .ancSet:   gotANC
            case .monitor:  false
        }
        if done { exit(0) }
    }

    func rfcommChannelClosed(_ ch: IOBluetoothRFCOMMChannel!) { exit(0) }

    private func send(_ ch: IOBluetoothRFCOMMChannel, _ bytes: [UInt8]) {
        var buf = bytes; ch.writeSync(&buf, length: UInt16(buf.count))
    }
}

let session = Session(command)
var ch: IOBluetoothRFCOMMChannel?
device.openRFCOMMChannelAsync(&ch, withChannelID: CHANNEL, delegate: session)

RunLoop.main.run()
