# Android Macro GUI — Step 1: Screen Mirror

Real-time screen mirroring of your MuMu emulator (or any Android device/emulator)
in a web browser, using the scrcpy protocol over ADB, with click-to-tap already
wired up as the foundation for macros (step 2).

**NEW: Multi-Display Support** — Switch between virtual displays on MuMu Player!

## Why this approach

Plain `adb screencap` polling only gets ~3-8 fps because it PNG-encodes a full
screenshot every time. Instead this uses the same approach real scrcpy uses:
the device streams an H.264 video feed over the adb connection, which we decode
client-side and re-stream to the browser as MJPEG. This gets 30-60 fps with low
latency.

## Multi-Display Support (MuMu Feature)

MuMu Player supports running multiple apps simultaneously on separate virtual displays,
similar to Android's freeform window mode. This tool now lets you switch between them:

- **Display 0**: Main screen (home)
- **Display 6, 7, etc.**: Virtual displays for background apps

Simply:
1. Connect to your device
2. Select a display from the dropdown
3. Click **Switch Display** to view and control apps on different screens

All displays maintain the same 30-60 FPS performance.

## Window Capture Mode (fastest, MuMu-on-same-PC only)

If MuMu is running on the **same PC** as this app, you can skip ADB video
streaming entirely and mirror MuMu's own render window directly using the
Windows Graphics Capture API. Since it's a direct GPU frame handoff (no
network hop, no on-device H.264 encode, no client-side decode), it's
noticeably lower latency and much lighter on CPU than the ADB mirror path.

In the web GUI, switch the **Mirror source** toggle to **Window Capture
(fast)**, pick your MuMu window from the list, and click **Connect &
Capture Window**. You still need a device serial selected/connected (adb is
used for touch/tap/swipe/nav input — capturing pixels alone gives no way to
inject touches).

Requires `pywin32` and `windows-capture` (see `requirements.txt`) — Windows
only. If they're not installed, this mode is simply unavailable and ADB
mirroring still works as before.

**Quirks worth knowing:**
- MuMu's render window (titled "Android Device") is normally kept
  minimized/off-screen, and it actually **stops rendering while
  minimized** — so this mode automatically restores it when you connect.
  That means the window becomes visible on your desktop (separate from
  the normal MuMu Player window) while this mode is active. You can
  alt-tab away from it or move it aside, just don't re-minimize it via
  the taskbar or the mirrored feed will freeze.
- The captured window includes MuMu's own tab-bar/toolbar chrome above
  the actual Android content. The **Crop top (px)** field trims this off
  (default 40px) — adjust it if the mirrored image includes a sliver of
  the tab bar, or is missing a sliver of the top of the screen (this can
  vary a little with Windows display scaling/DPI).
- Multi-display switching (the dropdown/Switch Display button) is
  ADB-mode only — window capture always shows whatever MuMu itself is
  currently displaying in that window.

## Navigation buttons

Back / Home / Recents buttons in the sidebar send the standard Android
nav keyevents (`input keyevent 4/3/187`) via adb — these work in both
mirror modes, but note the keyevent goes to whichever display currently
has Android's focus, which may not always be the display you're
mirroring in Window Capture mode.

## Setup (conda, Python 3.11 — continuing from your existing env)

You already hit a build error installing `av` via pip. Get it from
conda-forge instead (prebuilt, no compiling):

```bash
conda activate MuMuEMU
conda install -c conda-forge "av>=9,<11"
pip install -r requirements.txt --no-deps
pip install adbutils scrcpy-client flask opencv-python numpy
```

If `pip install -r requirements.txt` alone works cleanly for you (no av
build errors), you can skip the two lines above and just run:

```bash
pip install -r requirements.txt
```

## Connect MuMu to ADB

MuMu's built-in ADB usually listens on `127.0.0.1:7555` by default
(check MuMu's settings if different, some versions use other ports).

```bash
adb connect 127.0.0.1:7555
adb devices     # confirm it shows up as "device", not "offline"
```

## Run

```bash
python app.py
```

Open `http://localhost:5000` in your browser. Click **Refresh device list**,
pick your MuMu serial (e.g. `127.0.0.1:7555`), and click **Connect & Mirror**.
Or type the serial directly into the manual box.

Clicking anywhere on the mirrored screen sends a real tap to the device at the
correct scaled coordinates.

### Switching Displays

Once connected, you'll see a **Display (Virtual Screens)** dropdown in the sidebar
showing all available displays on the device. Select a display and click
**Switch Display** to view and interact with apps on that screen.

## Notes / troubleshooting

- If the video feed stays blank, check the terminal running `server.py` for
  scrcpy connection errors — usually means adb isn't actually connected to
  that serial, or MuMu's ADB debugging is off.
- `max_fps` and `bitrate` are set in `app.py` (`connect_device()`) — lower
  the bitrate if you're on a slow connection to the emulator.
- Multiple browser tabs will each pull their own MJPEG stream from the same
  decoded frame buffer — fine for personal use, not built for many concurrent
  viewers.
- **Latency:** `gen_frames()` pushes each frame to the browser the instant
  it's decoded (event-driven, no polling delay), and `JPEG_QUALITY` in
  `app.py` (default 70) trades a bit of image quality for smaller/faster
  frames. Even so, expect roughly 100-300ms of end-to-end lag — most of it
  is the WiFi ADB round-trip (`192.168.1.x:5555`) plus H.264 encode on the
  device and decode in Python, not something this app's code controls.
  If you need lower latency:
    - Connect over USB instead of WiFi ADB if possible (`adb devices` will
      show a USB serial instead of an IP:port) — this alone typically cuts
      the largest chunk of the delay.
    - Lower the bitrate (e.g. `bitrate=4_000_000`) — less data to
      encode/decode per frame.
    - Try `max_fps=30` in `connect_device()` — fewer frames to encode can
      reduce encoder queueing under CPU pressure.
- Display enumeration uses `adb shell dumpsys display` — if it fails to find
  displays, the tool defaults to display 0. Check your device output with
  `adb shell dumpsys display | grep "HWC display"` to debug.
- **Important quirk on MuMu:** the HWC/port numbers you see from
  `adb shell dumpsys SurfaceFlinger --display-id` (e.g. "HWC display 6/7")
  are **not** the same IDs the scrcpy-server needs. See "Multi-Display
  Architecture" below for why, and how this tool handles it automatically.

## Multi-Display Architecture

**The HWC-vs-logical-display-id quirk:**

MuMu's `dumpsys SurfaceFlinger --display-id` reports each virtual screen's
*HWC (hardware composer) port*, e.g.:
```
Display 4619827820427265280 (HWC display 0): port=0 ... displayName="mumuscreen000"
Display 4619827052952829958 (HWC display 6): port=6 ... displayName="mumuscreen006"
Display 4619827621058019847 (HWC display 7): port=7 ... displayName="mumuscreen007"
```
But the bundled scrcpy-server (v1.20, from the `scrcpy-client` PyPI package)
targets a display by calling Android's
`DisplayManager.getDisplay(displayId)`, which uses a completely different,
independently-assigned **logical display ID** space. On a typical MuMu
instance the mapping looks like:

| HWC port (what you see) | Android logical display id (what scrcpy needs) |
|---|---|
| 0 | 0 |
| 6 | 7 |
| 7 | 8 |

Passing the HWC port straight to the old scrcpy-server makes
`getDisplay()` return null, which crashes the server before it opens its
video socket — that shows up client-side as `ConnectionError: Failed to
connect scrcpy-server after 3 seconds`.

`get_available_displays()` in `app.py` resolves this automatically by
parsing `adb shell dumpsys display`, correlating each logical display's
`mDisplayId=` with its `address {port=...}` entry, and using the logical
id internally while still labeling the UI dropdown with the familiar HWC
port number. You never need to think about this — just pick "Display 6"
or "Display 7" from the dropdown as expected.

**Backend (`app.py`):**
- `get_available_displays(serial)` — Queries `dumpsys display`, maps HWC port -> logical display id
- `DisplayClient` — subclass of `scrcpy.Client` that patches the server launch command to target a specific logical display id (the upstream library hardcodes `0`)
- `_kill_stale_scrcpy_server(serial)` — kills any leftover scrcpy-server process on the device before reconnecting (`Client.stop()` doesn't reliably kill the remote process)
- `connect_device(serial, display_id)` — Connects scrcpy to a specific display
- `/displays` endpoint — Returns list of `{id, port}` objects (logical id + HWC port) for available displays
- `/switch_display` endpoint — Switches to a different display without disconnecting

**Frontend (`templates/index.html`):**
- Display selector dropdown (hidden until connected), labeled by HWC port but submitting the logical id
- "Switch Display" button for instant display switching
- Status bar shows current display's HWC port and resolution

**Performance:**
- All displays stream at 30-60 FPS with 8Mbps bitrate (configurable)
- Switching displays takes ~1-2 seconds (new connection to target display)
- Touch input automatically targets the correct display

## What's next (macros)

The `/tap` and `/swipe` endpoints already exist server-side. Step 2 will add:
- A recorder that captures a sequence of taps/swipes/waits while you interact
  with the mirror
- Saving/loading named macros (JSON)
- A playback loop with configurable repeat count / interval
- A simple macro editor in the sidebar
- **Multi-display macros** — record/play macros across multiple displays

