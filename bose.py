#!/usr/bin/env python3
"""
Bose QC35 II macOS controller — no phone app needed.

Usage:
  python bose_qc35.py list                     find paired Bose devices
  python bose_qc35.py status                   ANC level + battery %
  python bose_qc35.py anc high|low|off         change noise cancellation
  python bose_qc35.py monitor                  raw message stream (protocol debug)
  python bose_qc35.py name "My QC35"           rename the headphones

Pass --address XX:XX:XX:XX:XX:XX to target a specific device; the first
connected Bose device is auto-detected when omitted.

FIRST-TIME SETUP (one-time only):
  macOS requires Bluetooth permission for terminal tools.
  1. Open System Settings → Privacy & Security → Bluetooth
  2. Click "+" → add Terminal (Applications/Utilities/Terminal.app)
     or iTerm2 / whatever terminal you use
  3. Make sure it's toggled ON
  4. Run the command again

  Alternatively reset all BT permissions (triggers re-prompt for all apps):
    tccutil reset Bluetooth

Requires: Python 3.10+, pyobjc-core, pyobjc-framework-Cocoa
  pip install pyobjc-core pyobjc-framework-Cocoa
"""

import sys
import time
import ctypes
import threading
import argparse
import subprocess

import objc
from Foundation import NSObject, NSRunLoop, NSDate

# Load IOBluetooth (Classic Bluetooth, not BLE)
try:
    objc.loadBundle(
        "IOBluetooth",
        globals(),
        bundle_path="/System/Library/Frameworks/IOBluetooth.framework",
    )
except Exception as exc:
    sys.exit(f"Could not load IOBluetooth: {exc}")

# ── Protocol constants ────────────────────────────────────────────────────────
# QC35 / QC35 II: Classic Bluetooth RFCOMM channel 8.
# Byte sequences from community reverse-engineering of the Bose headphones protocol.
# Use `monitor` to see all raw messages if you need to adjust these.

RFCOMM_CHANNEL = 8

CMD_ANC_GET  = b"\x01\x01\x01\x03"
CMD_ANC_HIGH = b"\x01\x06\x02\x01\x03"
CMD_ANC_LOW  = b"\x01\x06\x02\x03\x03"
CMD_ANC_OFF  = b"\x01\x06\x02\x00\x03"
ANC_SET_CMDS = {"high": CMD_ANC_HIGH, "low": CMD_ANC_LOW, "off": CMD_ANC_OFF}
ANC_NAMES    = {0x00: "Off", 0x01: "High", 0x03: "Low"}

CMD_BATT_GET = b"\x02\x02\x01\x03"
CMD_NAME_GET = b"\x01\x07\x01\x03"


def make_name_cmd(name: str) -> bytes:
    encoded = name.encode("utf-8")[:20]
    return bytes([0x01, 0x07, len(encoded) + 1]) + encoded + b"\x03"


# ── IOBluetooth delegate ──────────────────────────────────────────────────────

class _BoseDelegate(NSObject):
    def init(self):
        self = objc.super(_BoseDelegate, self).init()
        if self is None:
            return None
        self.open_event  = threading.Event()
        self.open_status = None
        self._queue      = []
        self._lock       = threading.Lock()
        self.closed      = False
        return self

    def rfcommChannelOpenComplete_status_(self, channel, status):
        self.open_status = status
        self.open_event.set()

    def rfcommChannelData_data_length_(self, channel, data, length):
        raw = _read_void_ptr(data, length)
        if raw:
            with self._lock:
                self._queue.append(raw)

    def rfcommChannelClosed_(self, channel):
        self.closed = True

    def pop(self):
        with self._lock:
            return self._queue.pop(0) if self._queue else None


def _read_void_ptr(data, length: int) -> bytes:
    if length <= 0:
        return b""
    try:
        buf = (ctypes.c_uint8 * length).from_address(data)
        return bytes(buf)
    except TypeError:
        pass
    try:
        return bytes(data[:length])
    except Exception:
        return b""


# ── Connection class ──────────────────────────────────────────────────────────

class Bose:
    def __init__(self, address: str):
        self.address   = address
        self._channel  = None
        self._delegate = None

    def connect(self):
        device = IOBluetoothDevice.deviceWithAddressString_(self.address)
        if device is None:
            raise RuntimeError(f"Device not found: {self.address}")
        if not device.isConnected():
            raise RuntimeError(
                f"Device {self.address} is paired but not connected.\n"
                "  Connect via System Settings → Bluetooth, then try again."
            )
        self._delegate = _BoseDelegate.alloc().init()
        result = device.openRFCOMMChannelSync_withChannelID_delegate_(
            None, RFCOMM_CHANNEL, self._delegate
        )
        if isinstance(result, (tuple, list)) and len(result) >= 2:
            status, self._channel = int(result[0]), result[1]
        else:
            status, self._channel = int(result), None
        if status != 0 or self._channel is None:
            raise RuntimeError(
                f"Could not open RFCOMM control channel (status={status:#010x}).\n"
                "  Only one app can hold the control channel at a time.\n"
                "  Make sure no other Bose app is open on this Mac."
            )

    def send(self, cmd: bytes):
        self._channel.writeSync_length_(cmd, len(cmd))

    def recv(self, timeout: float = 2.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            msg = self._delegate.pop()
            if msg:
                return msg
            remaining = deadline - time.monotonic()
            NSRunLoop.currentRunLoop().runUntilDate_(
                NSDate.dateWithTimeIntervalSinceNow_(min(0.04, remaining))
            )
        return None

    def recv_all(self, timeout: float = 2.0) -> list:
        out, deadline = [], time.monotonic() + timeout
        while True:
            msg = self.recv(timeout=max(0, deadline - time.monotonic()))
            if msg is None:
                break
            out.append(msg)
            deadline = max(deadline, time.monotonic() + 0.3)
        return out

    def close(self):
        if self._channel:
            try:
                self._channel.closeChannel()
            except Exception:
                pass
            self._channel = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


# ── Device listing via system_profiler (no BT permission required) ────────────

_SP_CACHE = None

def _system_profiler_bt():
    global _SP_CACHE
    if _SP_CACHE is None:
        try:
            _SP_CACHE = subprocess.check_output(
                ["system_profiler", "SPBluetoothDataType"],
                stderr=subprocess.DEVNULL, timeout=8,
            ).decode()
        except Exception:
            _SP_CACHE = ""
    return _SP_CACHE


def _parse_bt_devices(text: str) -> list:
    """
    Parse system_profiler SPBluetoothDataType output.
    Indentation (spaces): 6 = sections, 10 = device names, 14 = properties.
    """
    devices = []
    in_devices     = False
    connected_flag = False
    current        = None

    def _save():
        if current:
            devices.append(dict(current))

    for line in text.splitlines():
        if not line.strip():
            continue
        indent   = len(line) - len(line.lstrip())
        stripped = line.strip()

        if indent == 6 and stripped.endswith(":"):
            sl = stripped.lower()
            if sl in ("connected:", "not connected:"):
                _save()
                current        = None
                in_devices     = True
                connected_flag = "not" not in sl
            continue

        if in_devices and indent == 10 and stripped.endswith(":"):
            _save()
            current = {
                "name":       stripped.rstrip(":"),
                "connected":  connected_flag,
                "address":    None,
                "minor_type": None,
                "vendor_id":  None,
                "firmware":   None,
            }
            continue

        if current and indent == 14 and ":" in stripped:
            key, _, val = stripped.partition(":")
            val = val.strip()
            kl  = key.strip().lower()
            if kl == "address":
                current["address"] = val
            elif kl == "minor type":
                current["minor_type"] = val
            elif kl == "vendor id":
                current["vendor_id"] = val.split()[0]
            elif kl == "firmware version":
                current["firmware"] = val

    _save()
    return devices


_BOSE_VENDOR_IDS = {"0x009e"}

def _is_bose(d: dict) -> bool:
    if d.get("vendor_id") and d["vendor_id"].lower() in _BOSE_VENDOR_IDS:
        return True
    return "bose" in d["name"].lower()


def _bose_devices() -> list:
    return [d for d in _parse_bt_devices(_system_profiler_bt()) if _is_bose(d)]


def _auto_address(explicit):
    if explicit:
        return explicit
    devices = _bose_devices()
    connected = [d for d in devices if d["connected"] and d["address"]]
    if not connected:
        not_conn = [d for d in devices if not d["connected"]]
        if not_conn:
            names = ", ".join(d["name"] for d in not_conn)
            sys.exit(
                f"Bose device(s) found but not connected: {names}\n"
                "Connect via System Settings → Bluetooth first."
            )
        sys.exit("No paired Bose devices found. Pair via System Settings → Bluetooth.")
    if len(connected) > 1:
        print("Multiple connected Bose devices — pass --address to choose one:")
        for d in connected:
            print(f"  {d['name']:<32}  {d['address']}")
        sys.exit(1)
    return connected[0]["address"]


# ── Response parsers ──────────────────────────────────────────────────────────

def _hex(b: bytes) -> str:
    return " ".join(f"{x:02x}" for x in b)


def _parse_anc(msg: bytes):
    if len(msg) >= 5 and msg[0] == 0x01 and msg[1] == 0x01:
        return ANC_NAMES.get(msg[4])
    return None


def _parse_battery(msg: bytes):
    if len(msg) >= 4 and msg[0] == 0x02 and msg[1] == 0x02:
        pct = msg[3]
        if 0 <= pct <= 100:
            return pct
    return None


# ── Subprocess wrapper (catches Bluetooth permission crash) ───────────────────

_WORKER_FLAG = "--_bt_worker"

def _permission_error():
    print(
        "\n  Bluetooth permission required.\n\n"
        "  One-time setup:\n"
        "    1. System Settings → Privacy & Security → Bluetooth\n"
        "    2. Click '+' → add Terminal (or iTerm2, Warp, etc.)\n"
        "    3. Toggle it ON\n"
        "    4. Run the command again\n\n"
        "  Or reset all Bluetooth permissions to re-trigger the prompt:\n"
        "    tccutil reset Bluetooth\n",
        file=sys.stderr,
    )


def _bt_subprocess(args) -> int:
    """
    Run a BT-using command in a child process so that a Bluetooth permission
    crash (SIGABRT) is caught here and shown as a helpful message.

    When a process is killed by SIGABRT, subprocess returns returncode = -6
    (negative signal number on Unix/macOS).
    """
    import signal as _signal
    child_argv = [sys.executable, __file__, _WORKER_FLAG] + sys.argv[1:]
    result = subprocess.run(child_argv)
    if result.returncode == -_signal.SIGABRT:  # -6 on macOS
        _permission_error()
        return 1
    return result.returncode


# ── Sub-commands ──────────────────────────────────────────────────────────────

def do_list(args):
    devices = _bose_devices()
    if not devices:
        print("No paired Bose devices found.")
        print("Pair via System Settings → Bluetooth, then try again.")
        return
    print(f"{'Device':<32}  {'Address':<20}  Status")
    print("─" * 62)
    for d in devices:
        st = "● connected" if d["connected"] else "○ not connected"
        print(f"{d['name']:<32}  {d['address'] or '?':<20}  {st}")
        if d.get("firmware"):
            print(f"  {'':32}  firmware {d['firmware']}")
    print()
    connected = [d for d in devices if d["connected"] and d["address"]]
    if connected:
        ex = connected[0]["address"]
        print("Quick-start:")
        print(f"  python bose_qc35.py status   --address {ex}")
        print(f"  python bose_qc35.py anc high --address {ex}")


def _do_status(args):
    address = _auto_address(args.address)
    print(f"Connecting to {address} …")
    with Bose(address) as dev:
        dev.connect()

        dev.send(CMD_ANC_GET)
        anc = None
        for _ in range(6):
            msg = dev.recv(1.5)
            if msg:
                anc = _parse_anc(msg)
                if anc:
                    break
                if args.debug:
                    print(f"  [raw] {_hex(msg)}")
        print(f"  ANC:     {anc or '(no response)'}")

        dev.send(CMD_BATT_GET)
        batt = None
        for _ in range(6):
            msg = dev.recv(1.5)
            if msg:
                batt = _parse_battery(msg)
                if batt is not None:
                    break
                if args.debug:
                    print(f"  [raw] {_hex(msg)}")
        print(f"  Battery: {f'{batt}%' if batt is not None else '(no response)'}")


def _do_anc(args):
    level   = args.level.lower()
    address = _auto_address(args.address)
    print(f"Connecting to {address} …")
    with Bose(address) as dev:
        dev.connect()
        dev.send(ANC_SET_CMDS[level])
        time.sleep(0.2)
        dev.send(CMD_ANC_GET)
        confirmed = None
        for _ in range(6):
            msg = dev.recv(1.0)
            if msg:
                confirmed = _parse_anc(msg)
                if confirmed:
                    break
                if args.debug:
                    print(f"  [raw] {_hex(msg)}")
        if confirmed:
            print(f"ANC → {confirmed}")
        else:
            print("Command sent (run `status` to verify).")


def _do_name(args):
    address = _auto_address(args.address)
    print(f"Connecting to {address} …")
    with Bose(address) as dev:
        dev.connect()
        dev.send(make_name_cmd(args.name))
        time.sleep(0.3)
    print(f"Name sent: {args.name!r}")
    print("Reconnect headphones for the new name to appear in Bluetooth settings.")


def _do_monitor(args):
    address = _auto_address(args.address)
    print(f"Connecting to {address} …")
    print("Monitoring.  Ctrl-C to stop.\n")
    with Bose(address) as dev:
        dev.connect()
        dev.send(CMD_ANC_GET)
        dev.send(CMD_BATT_GET)
        dev.send(CMD_NAME_GET)
        try:
            while True:
                msg = dev.recv(0.5)
                if msg:
                    label = ""
                    anc   = _parse_anc(msg)
                    batt  = _parse_battery(msg)
                    if anc:
                        label = f"  → ANC: {anc}"
                    elif batt is not None:
                        label = f"  → Battery: {batt}%"
                    print(f"  [{time.strftime('%H:%M:%S')}] {_hex(msg)}{label}")
        except KeyboardInterrupt:
            print("\nDone.")


# ── Argument parsing ──────────────────────────────────────────────────────────

def _build_parser():
    ap = argparse.ArgumentParser(
        prog="bose_qc35",
        description="Control Bose QC35 II from macOS — no phone app needed.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  python bose_qc35.py list
  python bose_qc35.py status
  python bose_qc35.py anc high
  python bose_qc35.py anc off
  python bose_qc35.py monitor
  python bose_qc35.py name "Pulkit's QC35"
  python bose_qc35.py anc low --address 78:2B:64:5B:CA:99
        """,
    )
    ap.add_argument("--address", "-a", metavar="XX:XX:XX:XX:XX:XX",
                    help="Bluetooth address (auto-detected if omitted)")
    ap.add_argument("--debug",   action="store_true",
                    help="Print raw bytes for unrecognised messages")
    ap.add_argument(_WORKER_FLAG, dest="worker", action="store_true",
                    default=False, help=argparse.SUPPRESS)

    sub = ap.add_subparsers(dest="cmd", metavar="COMMAND", required=True)
    sub.add_parser("list",    help="List paired Bose devices (no BT permission needed)")
    sub.add_parser("status",  help="Show ANC level and battery percentage")
    sub.add_parser("monitor", help="Stream all raw messages from headphones")

    p_anc = sub.add_parser("anc", help="Set noise-cancellation level")
    p_anc.add_argument("level", choices=["high", "low", "off"])

    p_name = sub.add_parser("name", help="Rename the headphones")
    p_name.add_argument("name", help="New device name (≤20 chars)")

    return ap


# ── Entry point ───────────────────────────────────────────────────────────────

BT_CMDS = {
    "status":  _do_status,
    "anc":     _do_anc,
    "name":    _do_name,
    "monitor": _do_monitor,
}


def main():
    ap   = _build_parser()
    args = ap.parse_args()

    if args.cmd == "list":
        do_list(args)
        return

    if not args.worker:
        # Shell-level wrapper: run ourselves as a subprocess so we can catch
        # the Bluetooth permission SIGABRT (exit 134) without crashing the UI.
        sys.exit(_bt_subprocess(args))

    # Worker mode: actually talk to the headphones
    try:
        BT_CMDS[args.cmd](args)
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
