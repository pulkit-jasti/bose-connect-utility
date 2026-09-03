<img src="cover.png" alt="Bose Connect" width="100%">

# Bose Connect

A lightweight macOS menu bar utility for Bose QC35 II headphones — control noise cancellation and monitor battery without the phone app.

---

## Why

The Bose QC35 II has two annoyances on macOS:

- The physical ANC button stops working during calls, making it impossible to turn off noise cancellation without reaching for your phone
- The headphones remember the last ANC setting, so they always reconnect at max noise cancellation even when you don't need it

Bose Connect fixes both. It sits in your menu bar, auto-disables ANC the moment your headphones connect, and lets you toggle it with one click.

---

## Features

- **Auto-disable ANC on connect** — headphones connect with ANC off by default, saving battery
- **One-click ANC control** — switch between High, Low, and Off from the menu bar
- **Battery monitor** — always visible next to the menu bar icon
- **Auto-hide** — the menu bar icon only appears when headphones are connected
- **Instant connect/disconnect detection** — no polling; reacts in real time via Bluetooth notifications
- **Launch at login** — toggle from within the app

---

## Requirements

- macOS 13 Ventura or later
- Bose QC35 II (or any QC35/QuietComfort headphones paired to your Mac)

---

## Installation

> **Note:** This app is not notarized (no Apple Developer account). macOS will warn you on first launch. This is expected — follow the steps below.

1. Download the latest `.dmg` from the [Releases](../../releases) page
2. Open the DMG and drag **BoseConnect.app** to your Applications folder
3. Right-click the app → **Open** → **Open** again in the dialog

You only need to do step 3 once. After that it launches normally.

Alternatively: if macOS blocks it, go to **System Settings → Privacy & Security** → scroll down → click **Open Anyway**.

---

## Usage

Once running, the app lives entirely in the menu bar — there's no Dock icon.

| Menu bar shows | Meaning |
|---|---|
| *(nothing)* | Headphones not connected |
| `〰 72%` | Connected, ANC not yet set by app |
| `〰 72% · Off` | Connected, ANC off |

Click the icon to open the panel:

- **Segmented ANC picker** — High / Low / Off, applied instantly
- **Battery** — updates on each connection
- **Launch at Login** — toggle auto-start
- **Refresh** — manually re-fetch battery
- **Quit** — close the app

---

## Build from Source

```bash
git clone https://github.com/pulkit-jasti/bose-connect-utility.git
cd bose-connect-utility
open BoseConnect.xcodeproj
```

Then hit **Cmd+R** in Xcode. Requires Xcode 16 or later.

---

## How It Works

The app communicates with the headphones over Classic Bluetooth RFCOMM (channel 9), the same protocol the official Bose app uses. On each connection it sends a bundled handshake + ANC command + battery request in a single write — the headphones reject commands sent separately. Bluetooth connect/disconnect events are delivered instantly via `IOBluetooth` system notifications, so no polling is needed.

---

## License

MIT — do whatever you want with it.
