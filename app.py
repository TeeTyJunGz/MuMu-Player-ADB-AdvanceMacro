"""
Android Emulator Web Macro GUI - Backend
Step 1: Real-time screen mirror over ADB using scrcpy protocol.
Step 2 (next): macro recording/playback on top of the tap/swipe controls below.
Multi-display support: Switch between virtual displays on MuMu Player.
"""

import os
import threading
import time
import re
import signal
import atexit

# pyrefly: ignore [missing-import]
import adbutils
import cv2
import numpy as np
from flask import Flask, Response, jsonify, render_template, request

import scrcpy

# Optional dependency: native window capture (Windows Graphics Capture API)
# used by "window" mirror mode below. Only available on Windows with
# pywin32 + windows-capture installed. ADB mirror mode works fine without
# these, so we degrade gracefully if they're missing.
try:
    import win32gui
    import win32con
    from windows_capture import WindowsCapture, Frame, InternalCaptureControl
    WINDOW_CAPTURE_AVAILABLE = True
except ImportError:
    WINDOW_CAPTURE_AVAILABLE = False

app = Flask(__name__)

from macros.models import Macro, MacroNode, Connection
from macros.storage import MacroStorage
from macros.executor import MacroExecutor

# Global executor reference
current_executor = None

adb = adbutils.AdbClient(host="127.0.0.1", port=5037)


class DisplayClient(scrcpy.Client):
    """
    scrcpy.Client (py-scrcpy-client 0.4.1) hardcodes "0" as the display id
    in its server launch command, with no constructor parameter to change
    it. MuMu Player exposes extra virtual displays (e.g. 6, 7) for
    background/multi-app windows, so we subclass and override the private
    server-deploy step to inject a configurable display id.

    We reimplement `_deploy_server`/`start` rather than patching the
    installed package, so this keeps working across reinstalls/upgrades
    of the scrcpy-client library. Mangled private attributes/methods of
    the parent class (`_Client__xxx`) are accessed explicitly by name,
    since normal `self.__xxx` name-mangling inside this subclass would
    bind to `_DisplayClient__xxx` instead.
    """

    def __init__(self, *args, display_id: int = 0, **kwargs):
        self.display_id = display_id
        super().__init__(*args, **kwargs)

    def _deploy_server(self) -> None:
        jar_name = "scrcpy-server.jar"
        server_file_path = os.path.join(
            os.path.dirname(scrcpy.core.__file__), jar_name
        )
        self.device.sync.push(server_file_path, f"/data/local/tmp/{jar_name}")
        commands = [
            f"CLASSPATH=/data/local/tmp/{jar_name}",
            "app_process",
            "/",
            "com.genymobile.scrcpy.Server",
            "1.20",  # Scrcpy server version
            "info",  # Log level
            f"{self.max_width}",
            f"{self.bitrate}",
            f"{self.max_fps}",
            f"{self.lock_screen_orientation}",
            "true",  # Tunnel forward
            "-",  # Crop
            "false",  # Send frame rate to client
            "true",  # Control enabled
            f"{self.display_id}",  # <-- the actual fix: target display id
            "false",  # Show touches
            "true" if self.stay_awake else "false",
            "-",  # Codec options
            self.encoder_name or "-",
            "false",  # Power off screen after server closed
        ]
        # Mangled attribute from parent class: _Client__server_stream
        self._Client__server_stream = self.device.shell(commands, stream=True)
        self._Client__server_stream.read(10)

    def start(self, threaded: bool = False, daemon_threaded: bool = False) -> None:
        assert self.alive is False
        self._deploy_server()
        # Mangled parent methods, called explicitly by their mangled name
        self._Client__init_server_connection()
        self.alive = True
        self._Client__send_to_listeners(scrcpy.EVENT_INIT)
        if threaded or daemon_threaded:
            self.stream_loop_thread = threading.Thread(
                target=self._Client__stream_loop, daemon=daemon_threaded
            )
            self.stream_loop_thread.start()
        else:
            self._Client__stream_loop()


# Shared mutable state for the currently connected device/client
state = {
    "client": None,       # scrcpy.Client instance (mode == "adb")
    "serial": None,       # connected device serial (used for input in both modes)
    "frame": None,         # latest decoded BGR frame (numpy array)
    "resolution": None,   # (width, height) of the current frame
    "display_id": 0,      # current display ID (default is main display, ADB mode only)
    "available_displays": [],  # list of available display IDs
    "mode": "adb",        # "adb" (scrcpy mirror) or "window" (native window capture)
    "window_capture_control": None,  # windows_capture.CaptureControl for the active capture
    "hwnd": None,   # HWND currently being captured
    "window_crop_top": 0,  # pixels cropped off the top (MuMu's own tab-bar chrome)
    "window_capture_thread": None,  # Thread running the blocking capture.start() call
    "window_capture_stop_event": threading.Event(),  # Signal to stop the capture thread cleanly
    "control_client": None,  # Secondary scrcpy client (control-only, no video) for window mode input
}
frame_lock = threading.Lock()
# Signaled by on_frame() the instant a new decoded frame lands, so
# gen_frames() can push it immediately instead of polling on a timer.
frame_ready = threading.Event()

# JPEG quality (0-100) used to re-encode each decoded frame for the browser
# MJPEG stream. Lower = smaller/faster to encode+transfer (less latency),
# at the cost of visible compression artifacts. 80 looks good but adds
# some avoidable lag; 60-70 is a good latency/quality tradeoff for a
# control-mirror (as opposed to a screen-recording) use case.
JPEG_QUALITY = 70

# Default top-crop (in pixels) for "window" mirror mode. MuMu's own window
# includes a Chrome-like tab strip + toolbar above the actual Android
# content when you capture its top-level window directly (there's no
# separate child window we can target — Windows Graphics Capture only
# works on top-level windows). This is fixed UI chrome, not scaled with
# the Android resolution, so a constant works, but it can vary a little
# with Windows display scaling/DPI — adjust via the "Crop top" field in
# the web GUI if the mirrored image includes a sliver of tab bar or is
# missing a sliver of the top of the screen.
DEFAULT_WINDOW_CROP_TOP = 40


# frame_counter = {"n": 0, "last_log": 0.0}


def get_available_displays(serial: str):
    """
    Query the device for all displays and map Android's *logical* display
    IDs (what the bundled scrcpy-server v1.20 actually needs, via
    DisplayManager.getDisplay(id)) to the HWC/port numbers shown by
    `dumpsys SurfaceFlinger --display-id` (what a human recognizes, e.g.
    MuMu's "HWC display 6/7").

    These two ID spaces are NOT the same, and on MuMu specifically they
    don't even align: HWC display 6 maps to logical id 7, HWC display 7
    maps to logical id 8, etc. Passing the raw HWC number straight to the
    old scrcpy-server as-is makes it call DisplayManager.getDisplay(6),
    which returns null, crashing the server before it can start the video
    socket the client is waiting to connect to.

    We correlate the two by matching the physicalDisplayId reported by
    each "DisplayDeviceInfo{...address {port=P, ..., physicalDisplayId=ID}"
    entry against the "mDisplayId=X ... address {port=P, ...}" entries in
    the "Logical Displays" section of `dumpsys display`.

    Returns a list of dicts: [{"id": <logical id for scrcpy>, "port": <HWC
    port, for display/labeling only>}, ...], sorted by port.
    """
    try:
        device = adb.device(serial)
        output = device.shell("dumpsys display")

        # Logical display blocks look like:
        #   mDisplayId=7
        #   ... ~330-340 chars of other mFoo=bar fields ...
        #   mBaseDisplayInfo=DisplayInfo{..., address {port=6, ...}, ...}
        # The gap sizes above vary across Android/MuMu builds (observed
        # ~80 chars on one device, ~330 on another), so use a generous
        # window rather than hardcoding an exact offset.
        pattern = re.compile(
            r"mDisplayId=(\d+).{0,2000}?mBaseDisplayInfo=DisplayInfo\{.{0,2000}?"
            r"address \{port=(\d+)",
            re.DOTALL,
        )

        seen = {}
        for logical_id_str, port_str in pattern.findall(output):
            logical_id = int(logical_id_str)
            port = int(port_str)
            seen.setdefault(logical_id, port)  # keep first match per id

        displays = [{"id": lid, "port": port} for lid, port in seen.items()]
        displays.sort(key=lambda d: d["port"])

        print(f"[displays] Found {len(displays)} displays (logical id -> port): "
              f"{[(d['id'], d['port']) for d in displays]}")

        if displays:
            return displays

        print("[displays] No displays parsed, defaulting to [{'id': 0, 'port': 0}]")
        return [{"id": 0, "port": 0}]
    except Exception as e:
        print(f"[get_available_displays ERROR] {e}")
        import traceback
        traceback.print_exc()
        # Return default display if query fails
        return [{"id": 0, "port": 0}]


def on_frame(frame):
    """Callback fired by scrcpy client whenever a new decoded frame arrives."""
    try:
        if frame is not None:
            with frame_lock:
                state["frame"] = frame
                state["resolution"] = (frame.shape[1], frame.shape[0])  # (w, h)
            # Wake up gen_frames() immediately instead of making it poll on
            # a fixed timer — cuts avg extra latency and stops it from
            # re-encoding/re-sending a stale frame while waiting.
            frame_ready.set()
            # frame_counter["n"] += 1
            now = time.time()
            # if now - frame_counter["last_log"] > 2:
                # print(f"[frame] count={frame_counter['n']} res={state['resolution']} display={state['display_id']}")
                # frame_counter["last_log"] = now 
    except Exception as e:
        # scrcpy-client swallows exceptions raised inside this callback,
        # which is exactly the kind of thing that causes a silent freeze.
        print(f"[on_frame ERROR] {e!r}")


# window_frame_counter = {"n": 0, "last_log": 0.0}


def list_capture_windows():
    """
    Enumerate visible top-level windows that look like MuMu instances, for
    the "window" mirror mode's window picker. Returns [{"hwnd": int, "title": str}].
    """
    if not WINDOW_CAPTURE_AVAILABLE:
        return []

    results = []

    def cb(hwnd, _):
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return
        # MuMu's per-instance render window is titled "Android Device"
        # (sometimes "Android Device-1", "-2", ... for extra instances).
        if "android device" in title.lower():
            results.append({"hwnd": hwnd, "title": title})

    win32gui.EnumWindows(cb, None)
    return results


def _on_window_frame(frame, capture_control):
    """Callback fired by windows_capture whenever a new captured frame lands."""
    try:
        # Stash the control object the first time we see it — this is how
        # we get a handle to stop this specific capture session later (the
        # object returned by capture.start() itself is just None; start()
        # blocks until the session ends, so the *callback* is the only
        # place we're handed a controllable reference).
        state["window_capture_control"] = capture_control

        buf = frame.frame_buffer  # BGRA numpy array, shape (h, w, 4)
        crop_top = state.get("window_crop_top", 0)
        if crop_top > 0 and buf.shape[0] > crop_top:
            buf = buf[crop_top:]
        bgr = cv2.cvtColor(buf, cv2.COLOR_BGRA2BGR)

        with frame_lock:
            state["frame"] = bgr
            state["resolution"] = (bgr.shape[1], bgr.shape[0])
        frame_ready.set()

        # window_frame_counter["n"] += 1
        now = time.time()
        # if now - window_frame_counter["last_log"] > 2:
            # print(f"[window_frame] count={window_frame_counter['n']} res={state['resolution']}")
            # window_frame_counter["last_log"] = now
    except Exception as e:
        print(f"[_on_window_frame ERROR] {e!r}")


def stop_window_capture():
    """Stop any active window-capture session (no-op if none active)."""
    control = state.get("window_capture_control")
    thread = state.get("window_capture_thread")
    ctrl_client = state.get("control_client")
    
    if control is not None:
        try:
            control.stop()
        except Exception as e:
            print(f"[stop_window_capture] warning: {e}")
    
    # Close the control-only scrcpy client
    if ctrl_client is not None:
        try:
            ctrl_client.stop()
        except Exception:
            pass
        state["control_client"] = None
    
    # Signal the capture thread to stop and wait for it to exit cleanly
    if thread is not None:
        state["window_capture_stop_event"].set()
        try:
            # Give the thread up to 3 seconds to exit cleanly
            thread.join(timeout=3.0)
            if thread.is_alive():
                print("[stop_window_capture] warning: capture thread did not exit in time (daemon, will be terminated on shutdown)")
        except Exception as e:
            print(f"[stop_window_capture] thread join error: {e}")
        state["window_capture_thread"] = None
    
    state["window_capture_control"] = None
    state["window_hwnd"] = None
    state["window_capture_stop_event"].clear()



def start_window_capture(hwnd: int, crop_top: int = DEFAULT_WINDOW_CROP_TOP):
    """
    Start mirroring by directly capturing MuMu's own render window via the
    Windows Graphics Capture API (windows-capture package), instead of
    streaming H.264 over ADB/scrcpy. Since everything runs on the same PC,
    this skips ADB entirely for video — no network hop, no on-device H.264
    encode, no client-side decode — just a GPU-to-GPU frame handoff, which
    is both lower latency and far lighter on CPU than the ADB mirror path.

    We also create a separate (hidden) scrcpy client for input/control only,
    using its persistent socket which is much faster (~5-10ms per tap) than
    spawning adb shell processes (~30-50ms per tap).

    Important quirk: MuMu keeps this window "minimized" (off-screen) most
    of the time and, unlike some GPU apps, it actually *stops rendering*
    while iconic — so Windows Graphics Capture gets zero frames from it in
    that state (confirmed by testing: 0 frames/many seconds while iconic,
    ~60fps immediately after restoring). We restore it here so capture
    actually works; this does mean the "Android Device" window becomes
    visible on your desktop while this mode is active (separate from the
    normal MuMu Player window) — you can freely alt-tab away from it or
    move it aside, just don't re-minimize it via the taskbar or the video
    feed will freeze.
    """
    if not WINDOW_CAPTURE_AVAILABLE:
        raise RuntimeError(
            "Window capture isn't available — install pywin32 and windows-capture "
            "(pip install pywin32 windows-capture) and restart the server."
        )

    stop_window_capture()

    if win32gui.IsIconic(hwnd):
        win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
        time.sleep(0.3)  # give MuMu a moment to resume rendering

    # Create a secondary scrcpy client for control/input only (no video decoding overhead).
    # We start it without listening to frames, so it just opens the control channel
    # and sits there. This gives us ~5-10ms per tap via the persistent socket,
    # vs ~30-50ms per `adb shell input tap` spawn.
    try:
        ctrl_client = scrcpy.Client(device=state["serial"], max_fps=30)
        # Suppress the frame listener so we don't decode and store the video stream
        ctrl_client.add_listener(scrcpy.EVENT_FRAME, lambda f: None)
        ctrl_client.start(threaded=True)
        state["control_client"] = ctrl_client
        print("[start_window_capture] control-only scrcpy client started for low-latency input")
    except Exception as e:
        print(f"[start_window_capture] warning: failed to start control client: {e}, falling back to adb shell input")
        state["control_client"] = None

    capture = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=hwnd)

    @capture.event
    def on_frame_arrived(frame: "Frame", capture_control: "InternalCaptureControl"):
        _on_window_frame(frame, capture_control)

    @capture.event
    def on_closed():
        print("[window_capture] capture session closed (window closed/lost?)")
        state["window_capture_control"] = None

    def _run():
        try:
            capture.start()
        except Exception as e:
            print(f"[window_capture] capture thread ended: {e!r}")

    # Ensure any previous capture thread is fully cleaned up before starting a new one
    prev_thread = state.get("window_capture_thread")
    if prev_thread is not None and prev_thread.is_alive():
        print("[start_window_capture] waiting for previous capture thread to exit...")
        prev_thread.join(timeout=1.0)

    # Create and start the new thread (non-daemon, so we can properly join it)
    thread = threading.Thread(target=_run, daemon=False)
    thread.start()
    state["window_capture_thread"] = thread

    state["window_hwnd"] = hwnd
    state["window_crop_top"] = crop_top
    state["mode"] = "window"
    with frame_lock:
        state["frame"] = None
        state["resolution"] = None
    frame_ready.clear()


def ensure_adb_serial(serial: str):
    """
    Make sure `serial` is reachable over adb and populate available_displays,
    without starting an scrcpy video stream. Used by window-capture mode,
    which still needs adb for touch/nav input even though video comes from
    the window capture instead.
    """
    if state["serial"] != serial:
        state["available_displays"] = get_available_displays(serial)
    state["serial"] = serial


def _kill_stale_scrcpy_server(serial: str) -> None:
    """
    Best-effort cleanup of any leftover scrcpy-server process on the device.

    scrcpy.Client.stop() only closes the *local* adb socket ends; it does not
    reliably terminate the remote `app_process` running scrcpy-server.jar
    (that process doesn't read stdin, so closing the shell stream from our
    side doesn't kill it). A stale server keeps its abstract socket
    ("localabstract:scrcpy") open, so the next Client we start for a
    different display can end up connecting to the *old* (wrong-display)
    server instead, or time out entirely if it's already consumed its
    video+control connections. Killing leftover processes before every new
    connection avoids that.
    """
    try:
        device = adb.device(serial)
        device.shell(
            "for pid in $(ps -A 2>/dev/null | grep 'app_process.*scrcpy' "
            "| awk '{print $2}'); do kill -9 $pid; done"
        )
    except Exception as e:
        print(f"[_kill_stale_scrcpy_server] warning: {e}")


def connect_device(serial: str, display_id: int = 0):
    """
    Stop any existing client and connect to the given device serial on a specific display.

    Args:
        serial: Device serial (e.g., "127.0.0.1:7555")
        display_id: Android *logical* display ID to mirror (see
            get_available_displays() docstring — this is NOT the HWC port
            number shown by `dumpsys SurfaceFlinger --display-id`).
    """
    if state["client"] is not None:
        try:
            state["client"].stop()
        except Exception:
            pass
        state["client"] = None

    # Switching (back) to ADB mirror mode — stop any active window capture.
    stop_window_capture()
    state["mode"] = "adb"

    # Clean up any leftover server process before starting a new one, see
    # _kill_stale_scrcpy_server docstring for why this is necessary.
    _kill_stale_scrcpy_server(serial)
    time.sleep(0.3)

    # Always refresh available displays because new displays (emulator windows) 
    # could have been created since the last connection.
    state["available_displays"] = get_available_displays(serial)

    valid_ids = {d["id"] for d in state["available_displays"]}
    if display_id not in valid_ids:
        print(f"[connect_device WARNING] Display id {display_id} not available, using display 0")
        display_id = 0

    # Create scrcpy client targeting the requested display id
    client = DisplayClient(
        device=serial,
        max_fps=60,
        bitrate=8_000_000,
        display_id=display_id,
    )

    client.add_listener(scrcpy.EVENT_FRAME, on_frame)
    client.start(threaded=True)

    state["client"] = client
    state["serial"] = serial
    state["display_id"] = display_id
    with frame_lock:
        state["frame"] = None
        state["resolution"] = None
    frame_ready.clear()  # drop any stale "frame ready" signal from the old display


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/devices")
def devices():
    """List devices currently visible to adb (run `adb connect <ip:port>` first for MuMu)."""
    try:
        devs = [d.serial for d in adb.device_list()]
        return jsonify({"ok": True, "devices": devs})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/connect", methods=["POST"])
def connect():
    data = request.json or {}
    serial = data.get("serial")
    display_id = data.get("display_id", 0)
    
    if not serial:
        return jsonify({"ok": False, "error": "serial required"}), 400
    
    try:
        connect_device(serial, display_id=display_id)
        # give the client a moment to receive the first frame / resolution
        for _ in range(50):
            if state["resolution"] is not None:
                break
            time.sleep(0.1)
        return jsonify({
            "ok": True,
            "resolution": state["resolution"],
            "display_id": state["display_id"],
            "available_displays": state["available_displays"]
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/displays", methods=["POST"])
def get_displays():
    """Get list of available displays for a device."""
    serial = (request.json or {}).get("serial")
    if not serial:
        return jsonify({"ok": False, "error": "serial required"}), 400
    
    try:
        displays = get_available_displays(serial)
        return jsonify({"ok": True, "displays": displays})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/switch_display", methods=["POST"])
def switch_display():
    """Switch to a different display on the currently connected device."""
    display_id = (request.json or {}).get("display_id")
    if display_id is None:
        return jsonify({"ok": False, "error": "display_id required"}), 400
    
    if state["client"] is None or state["serial"] is None:
        return jsonify({"ok": False, "error": "not connected"}), 400
    
    try:
        display_id = int(display_id)
        connect_device(state["serial"], display_id=display_id)
        # Wait for first frame
        for _ in range(50):
            if state["resolution"] is not None:
                break
            time.sleep(0.1)
        return jsonify({
            "ok": True,
            "resolution": state["resolution"],
            "display_id": state["display_id"]
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/status")
def status():
    return jsonify({
        "connected": state["client"] is not None or state["window_capture_control"] is not None or state.get("headless"),
        "serial": state["serial"],
        "resolution": state["resolution"],
        "display_id": state["display_id"],
        "available_displays": state["available_displays"],
        "mode": state["mode"],
        "headless": state.get("headless", False),
        "window_capture_available": WINDOW_CAPTURE_AVAILABLE,
    })


@app.route("/toggle_headless", methods=["POST"])
def toggle_headless():
    """Toggle headless mode: stop video stream but keep ADB serial for macro execution."""
    try:
        going_headless = not state.get("headless", False)
        
        if going_headless:
            # Stop video streaming to save resources
            if state["client"] is not None:
                try:
                    state["client"].stop()
                except Exception:
                    pass
                state["client"] = None
            stop_window_capture()
            state["headless"] = True
            state["mode"] = "headless"
            with frame_lock:
                state["frame"] = None
                state["resolution"] = None
            print("[headless] Video stream stopped — macro-only mode active")
        else:
            # Re-enable video by reconnecting
            state["headless"] = False
            serial = state["serial"]
            if serial:
                connect_device(serial, display_id=state.get("display_id", 0))
                for _ in range(50):
                    if state["resolution"] is not None:
                        break
                    time.sleep(0.1)
            print("[headless] Video stream re-enabled")
        
        return jsonify({"ok": True, "headless": state.get("headless", False)})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/capture_windows")
def capture_windows():
    """List MuMu windows available for the 'window' (native capture) mirror mode."""
    if not WINDOW_CAPTURE_AVAILABLE:
        return jsonify({
            "ok": False,
            "error": "pywin32/windows-capture not installed on the server",
            "windows": [],
        })
    try:
        return jsonify({"ok": True, "windows": list_capture_windows()})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/connect_window", methods=["POST"])
def connect_window():
    """
    Switch to "window" mirror mode: capture MuMu's own render window
    directly instead of streaming video over ADB. Still requires a device
    serial (for touch/nav input via `adb shell input ...`).
    """
    data = request.json or {}
    serial = data.get("serial")
    hwnd = data.get("hwnd")
    crop_top = data.get("crop_top", DEFAULT_WINDOW_CROP_TOP)

    if not serial:
        return jsonify({"ok": False, "error": "serial required"}), 400
    if not hwnd:
        return jsonify({"ok": False, "error": "hwnd required"}), 400

    try:
        # Stop any running scrcpy client — window capture doesn't need it,
        # and keeping it alive would waste CPU on encode/decode for a
        # video feed we're no longer displaying.
        if state["client"] is not None:
            try:
                state["client"].stop()
            except Exception:
                pass
            state["client"] = None

        ensure_adb_serial(serial)
        start_window_capture(int(hwnd), crop_top=int(crop_top))

        for _ in range(50):
            if state["resolution"] is not None:
                break
            time.sleep(0.1)

        return jsonify({
            "ok": True,
            "resolution": state["resolution"],
            "mode": state["mode"],
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/nav", methods=["POST"])
def nav():
    """Android nav bar buttons: back / home / recents, via adb keyevent."""
    action = (request.json or {}).get("action")
    keyevents = {
        "back": 4,
        "home": 3,
        "recents": 187,
    }
    if action not in keyevents:
        return jsonify({"ok": False, "error": f"unknown action: {action}"}), 400
    if state["serial"] is None:
        return jsonify({"ok": False, "error": "not connected"}), 400

    try:
        adb.device(state["serial"]).shell(f"input keyevent {keyevents[action]}")
        return jsonify({"ok": True})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"ok": False, "error": str(e)}), 500


def gen_frames():
    """
    MJPEG generator: yields the latest frame as a multipart JPEG stream.

    Blocks on frame_ready (set by on_frame() the instant a new decoded
    frame lands) instead of polling on a fixed timer. This avoids both
    the ~8-16ms average extra latency a poll loop adds, and re-encoding/
    re-sending a stale frame while waiting for the next one — both of
    which show up as perceptible extra lag/jitter on the client side.
    """
    while True:
        got_frame = frame_ready.wait(timeout=0.5)
        if not got_frame:
            continue  # no new frame yet, keep waiting
        frame_ready.clear()

        with frame_lock:
            frame = state["frame"]
        if frame is None:
            continue

        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, JPEG_QUALITY])
        if not ok:
            continue
        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + buf.tobytes() + b"\r\n"
        )


@app.route("/video_feed")
def video_feed():
    return Response(gen_frames(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/tap", methods=["POST"])
def tap():
    """Single tap at device pixel coordinates (x, y)."""
    data = request.json or {}
    x, y = data.get("x"), data.get("y")
    if x is None or y is None:
        return jsonify({"ok": False, "error": "missing coords"}), 400

    if state["mode"] == "window":
        # Window capture mode can use either the control-only scrcpy client
        # (fast, ~5-10ms per tap via persistent socket) or fall back to adb shell.
        ctrl = state.get("control_client")
        if ctrl is not None:
            try:
                ctrl.control.touch(x, y, scrcpy.ACTION_DOWN)
                ctrl.control.touch(x, y, scrcpy.ACTION_UP)
                return jsonify({"ok": True})
            except Exception as e:
                print(f"[tap] control_client error: {e}, falling back to adb shell")
        
        # Fallback: use adb shell input (slower, ~30-50ms per tap)
        if state["serial"] is None:
            return jsonify({"ok": False, "error": "not connected"}), 400
        adb.device(state["serial"]).shell(f"input tap {int(x)} {int(y)}")
        return jsonify({"ok": True})

    if state["client"] is None:
        return jsonify({"ok": False, "error": "not connected"}), 400
    state["client"].control.touch(x, y, scrcpy.ACTION_DOWN)
    state["client"].control.touch(x, y, scrcpy.ACTION_UP)
    return jsonify({"ok": True})



@app.route("/swipe", methods=["POST"])
def swipe():
    """Swipe from (x1,y1) to (x2,y2) over duration_ms (used later by macros)."""
    data = request.json or {}
    try:
        x1, y1 = data["x1"], data["y1"]
        x2, y2 = data["x2"], data["y2"]
        duration_ms = data.get("duration_ms", 300)
    except KeyError:
        return jsonify({"ok": False, "error": "x1,y1,x2,y2 required"}), 400

    if state["mode"] == "window":
        # Try to use control-only scrcpy client if available (fast path)
        ctrl = state.get("control_client")
        if ctrl is not None:
            try:
                steps = max(2, duration_ms // 16)
                ctrl.control.touch(x1, y1, scrcpy.ACTION_DOWN)
                for i in range(1, steps + 1):
                    progress = i / steps
                    x = x1 + (x2 - x1) * progress
                    y = y1 + (y2 - y1) * progress
                    ctrl.control.touch(x, y, scrcpy.ACTION_MOVE)
                    time.sleep(duration_ms / 1000 / steps)
                ctrl.control.touch(x2, y2, scrcpy.ACTION_UP)
                return jsonify({"ok": True})
            except Exception as e:
                print(f"[swipe] control_client error: {e}, falling back to adb shell")
        
        # Fallback: use adb shell input
        if state["serial"] is None:
            return jsonify({"ok": False, "error": "not connected"}), 400
        adb.device(state["serial"]).shell(
            f"input swipe {int(x1)} {int(y1)} {int(x2)} {int(y2)} {int(duration_ms)}"
        )
        return jsonify({"ok": True})

    if state["client"] is None:
        return jsonify({"ok": False, "error": "not connected"}), 400

    steps = max(2, duration_ms // 16)
    client = state["client"]
    client.control.touch(x1, y1, scrcpy.ACTION_DOWN)
    for i in range(1, steps + 1):
        ix = x1 + (x2 - x1) * i / steps
        iy = y1 + (y2 - y1) * i / steps
        client.control.touch(int(ix), int(iy), scrcpy.ACTION_MOVE)
        time.sleep(duration_ms / 1000 / steps)
    client.control.touch(x2, y2, scrcpy.ACTION_UP)
    return jsonify({"ok": True})


@app.route("/api/macros", methods=["GET"])
def list_macros():
    """List all macros"""
    try:
        macro_ids = MacroStorage.list_all()
        macros = []
        for macro_id in macro_ids:
            macro = MacroStorage.load(macro_id)
            if macro:
                macros.append({
                    "id": macro.id,
                    "name": macro.name,
                    "description": macro.description,
                    "created_at": macro.created_at,
                    "modified_at": macro.modified_at,
                    "node_count": len(macro.nodes)
                })
        return jsonify({"ok": True, "macros": macros})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/macros", methods=["POST"])
def create_macro():
    """Create new macro"""
    try:
        data = request.json or {}
        macro = Macro(None, data.get("name", "Untitled"), data.get("description", ""))
        MacroStorage.save(macro)
        return jsonify({"ok": True, "macro": macro.to_dict()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/macros/reorder", methods=["POST"])
def reorder_macros():
    """Save macro order"""
    try:
        data = request.json or {}
        order = data.get("order", [])
        MacroStorage.save_order(order)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/macros/<macro_id>", methods=["GET"])
def get_macro(macro_id):
    """Get macro details"""
    try:
        macro = MacroStorage.load(macro_id)
        if not macro:
            return jsonify({"ok": False, "error": "Macro not found"}), 404
        return jsonify({"ok": True, "macro": macro.to_dict()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/macros/<macro_id>", methods=["PUT"])
def update_macro(macro_id):
    """Update macro"""
    try:
        macro = MacroStorage.load(macro_id)
        if not macro:
            return jsonify({"ok": False, "error": "Macro not found"}), 404
        
        data = request.json or {}
        macro.name = data.get("name", macro.name)
        macro.description = data.get("description", macro.description)
        
        # Update nodes and connections
        if "nodes" in data:
            macro.nodes = {}
            for node_data in data["nodes"]:
                node = MacroNode.from_dict(node_data.copy())
                macro.nodes[node.id] = node
        
        if "connections" in data:
            macro.connections = []
            for conn_data in data["connections"]:
                conn = Connection(conn_data["from"], conn_data["to"], conn_data.get("label", "default"))
                macro.connections.append(conn)
        
        MacroStorage.save(macro)
        return jsonify({"ok": True, "macro": macro.to_dict()})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/macros/<macro_id>", methods=["DELETE"])
def delete_macro(macro_id):
    """Delete a macro"""
    try:
        MacroStorage.delete(macro_id)
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/macros/<macro_id>/play", methods=["POST"])
def play_macro(macro_id):
    """Start macro playback"""
    global current_executor
    try:
        serial = request.json.get("serial") if request.json else None
        if not serial or serial != state["serial"]:
            return jsonify({"ok": False, "error": "Device not connected"}), 400
        
        macro = MacroStorage.load(macro_id)
        if not macro:
            return jsonify({"ok": False, "error": "Macro not found"}), 404
        
        if current_executor:
            try:
                current_executor.stop()
            except Exception:
                pass
                
        current_executor = MacroExecutor(
            macro, 
            serial, 
            get_frame_callback=lambda: state.get("frame")
        )
        current_executor.start()
        
        return jsonify({"ok": True, "status": "running"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/macros/<macro_id>/stop", methods=["POST"])
def stop_macro(macro_id):
    """Stop macro playback"""
    global current_executor
    try:
        if current_executor:
            current_executor.stop()
        return jsonify({"ok": True, "status": "stopped"})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

@app.route("/api/macros/<macro_id>/status", methods=["GET"])
def macro_status(macro_id):
    """Get macro playback status"""
    global current_executor
    try:
        if not current_executor:
            return jsonify({"ok": True, "status": "idle", "log": []})
        
        return jsonify({
            "ok": True,
            "status": current_executor.state,
            "current_node": current_executor.current_node_id,
            "log": current_executor.execution_log[-50:]  # Last 50 entries
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500

# Utility endpoints

@app.route("/api/color-picker", methods=["POST"])
def get_pixel_color():
    """Get pixel color at device coordinates from the current frame"""
    try:
        data = request.json or {}
        x, y = data.get("x"), data.get("y")
        if x is None or y is None:
            return jsonify({"ok": False, "error": "x, y required"}), 400
        with frame_lock:
            frame = state.get("frame")
        if frame is None:
            return jsonify({"ok": False, "error": "No frame available — device not connected"}), 400
        h, w = frame.shape[:2]
        # Clamp to frame bounds
        px = int(max(0, min(x, w - 1)))
        py = int(max(0, min(y, h - 1)))
        b, g, r = int(frame[py, px, 0]), int(frame[py, px, 1]), int(frame[py, px, 2])
        hex_color = "#{:02x}{:02x}{:02x}".format(r, g, b).upper()
        return jsonify({"ok": True, "x": px, "y": py, "hex": hex_color, "rgb": [r, g, b]})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


def _cleanup():
    """Forcefully clean up all background threads so the process can exit."""
    print("\n[shutdown] Cleaning up...")
    global current_executor
    # Stop any running macro
    if current_executor:
        try:
            current_executor.stop()
        except Exception:
            pass
        current_executor = None
    # Stop scrcpy client
    if state.get("client"):
        try:
            state["client"].stop()
        except Exception:
            pass
        state["client"] = None
    # Stop window capture
    try:
        stop_window_capture()
    except Exception:
        pass
    print("[shutdown] Done.")


atexit.register(_cleanup)


def _signal_handler(sig, frame):
    """Handle Ctrl+C: clean up and force-exit."""
    _cleanup()
    os._exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    app.run(host="0.0.0.0", port=5000, threaded=True)