"""
MuMuADB — Interactive CLI Runner
Vite-style interactive prompts for selecting device, display, and macro.
Press 'P' during execution to pause/resume, Ctrl+C to stop.
"""
import sys
import time
import threading
import msvcrt  # Windows only — for non-blocking keypresses during execution

import adbutils
import scrcpy
import questionary
from questionary import Style

from macros.storage import MacroStorage
from macros.executor import MacroExecutor
from app import DisplayClient, get_available_displays

# ─── Custom style matching a dark-mode vite-like look ────────────────────────
CLI_STYLE = Style([
    ("qmark",        "fg:#a78bfa bold"),   # purple question mark
    ("question",     "bold"),
    ("answer",       "fg:#34d399 bold"),   # green selected answer
    ("pointer",      "fg:#a78bfa bold"),   # purple arrow
    ("highlighted",  "fg:#a78bfa bold"),   # highlighted choice
    ("selected",     "fg:#34d399"),
    ("separator",    "fg:#6b7280"),
    ("instruction",  "fg:#6b7280 italic"),
    ("text",         ""),
    ("disabled",     "fg:#6b7280 italic"),
])

BANNER = r"""
  __  __      __  __       _    ___  ___
 |  \/  |_  _|  \/  |_  _/_\  |   \| _ )
 | |\/| | || | |\/| | || / _ \ | |) | _ \
 |_|  |_|\_,_|_|  |_|\_,_/_/ \_\|___/|___/

  Advanced Macro CLI  •  Arrow keys to select  •  Enter to confirm
"""


# ─── Helper: clear last N lines (for clean reprints) ─────────────────────────
def _section(title: str):
    print(f"\n  \033[35m◆\033[0m  {title}")


# ─── Step 1: Select ADB Device ───────────────────────────────────────────────
def select_device() -> str:
    _section("Scanning for ADB devices...")
    try:
        adb = adbutils.AdbClient(host="127.0.0.1", port=5037)
        devices = adb.device_list()
    except Exception as e:
        print(f"\n  \033[31m✖\033[0m  Could not reach ADB server: {e}")
        print("     Make sure 'adb server' is running (run `adb devices` first).")
        sys.exit(1)

    if not devices:
        print("\n  \033[31m✖\033[0m  No ADB devices found.")
        print("     Connect your device/emulator and run `adb devices` first.\n")
        sys.exit(1)

    choices = []
    for d in devices:
        state = d.info.get("state", "unknown") if hasattr(d, "info") and d.info else "device"
        choices.append(questionary.Choice(
            title=f"{d.serial}  ({state})",
            value=d.serial
        ))

    return questionary.select(
        "Select ADB device:",
        choices=choices,
        style=CLI_STYLE,
        instruction="  (use arrow keys, press Enter to select)",
    ).ask()


# ─── Step 2: Select Display ───────────────────────────────────────────────────
def select_display(serial: str) -> int:
    _section(f"Scanning displays on {serial}...")
    try:
        displays = get_available_displays(serial)
    except Exception as e:
        print(f"  \033[33m⚠\033[0m  Could not query displays ({e}). Defaulting to display 0.")
        return 0

    choices = [questionary.Choice(title="Display 0  (default / main screen)", value=0)]
    for d in displays:
        choices.append(questionary.Choice(
            title=f"Display {d['id']}  (Port: {d['port']})",
            value=d["id"]
        ))

    # Remove duplicates (display 0 might appear in the list)
    seen = set()
    unique_choices = []
    for c in choices:
        if c.value not in seen:
            seen.add(c.value)
            unique_choices.append(c)

    if len(unique_choices) == 1:
        print("  \033[90m→  Only default display 0 available.\033[0m")
        return 0

    return questionary.select(
        "Select display:",
        choices=unique_choices,
        style=CLI_STYLE,
        instruction="  (use arrow keys, press Enter to select)",
    ).ask()


# ─── Step 3: Select Macro ─────────────────────────────────────────────────────
def select_macro():
    _section("Loading saved macros...")
    all_ids = MacroStorage.list_all()
    macros = []
    for mid in all_ids:
        m = MacroStorage.load(mid)
        if m:
            macros.append(m)

    if not macros:
        print("  \033[31m✖\033[0m  No macros found. Create one in the Web GUI first.\n")
        sys.exit(1)

    choices = [
        questionary.Choice(
            title=f"{m.name}  ({len(m.nodes)} nodes)",
            value=m
        )
        for m in macros
    ]

    return questionary.select(
        "Select macro to run:",
        choices=choices,
        style=CLI_STYLE,
        instruction="  (use arrow keys, press Enter to select)",
    ).ask()


# ─── Execution Runner ─────────────────────────────────────────────────────────
class CLIHeadlessRunner:
    def __init__(self, macro, serial: str, display_id: int):
        self.macro = macro
        self.serial = serial
        self.display_id = display_id
        self.frame = None
        self.scrcpy_client = None
        self.executor = None
        self._pause_lock = threading.Lock()

    def on_frame(self, frame):
        if frame is not None:
            self.frame = frame

    def _keypress_listener(self):
        """Listen for 'P' key to pause/resume without blocking execution."""
        print("\n  \033[90mControls:  [P] Pause / Resume   [Ctrl+C] Stop\033[0m\n")
        while self.executor and self.executor.state in ("running", "paused"):
            if msvcrt.kbhit():
                ch = msvcrt.getwch()
                if ch.lower() == "p":
                    if self.executor.state == "running":
                        self.executor.pause()
                        print("\n  \033[33m⏸  Macro paused. Press P to resume.\033[0m\n")
                    elif self.executor.state == "paused":
                        self.executor.resume()
                        print("\n  \033[32m▶  Macro resumed.\033[0m\n")
            time.sleep(0.05)

    def start(self):
        print(f"\n  \033[35m◆\033[0m  Launching screen capture on display {self.display_id}...")
        self.scrcpy_client = DisplayClient(
            device=self.serial,
            display_id=self.display_id,
            max_fps=15,
            bitrate=1_000_000,
        )
        self.scrcpy_client.add_listener(scrcpy.EVENT_FRAME, self.on_frame)
        self.scrcpy_client.start(threaded=True)
        time.sleep(2)  # Wait for first frame

        print(f"  \033[35m◆\033[0m  Starting macro: \033[97m{self.macro.name}\033[0m")
        self.executor = MacroExecutor(
            self.macro,
            self.serial,
            get_frame_callback=lambda: self.frame,
        )
        self.executor.start()

        # Start keypress listener in background thread
        key_thread = threading.Thread(target=self._keypress_listener, daemon=True)
        key_thread.start()

        try:
            while self.executor.state in ("running", "paused"):
                # Drain log so it doesn't grow forever (executor already prints to console)
                while self.executor.execution_log:
                    self.executor.execution_log.pop(0)
                time.sleep(0.3)
        except KeyboardInterrupt:
            print("\n\n  \033[31m✖\033[0m  Stopping macro...")
            self.executor.stop()
            time.sleep(1)

        print("\n  \033[32m✔\033[0m  Execution finished.\n")
        if self.scrcpy_client:
            self.scrcpy_client.stop()


# ─── Main Entry ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print(f"\033[35m{BANNER}\033[0m")

    try:
        serial = select_device()
        if serial is None:
            sys.exit(0)

        display_id = select_display(serial)
        if display_id is None:
            sys.exit(0)

        macro = select_macro()
        if macro is None:
            sys.exit(0)

        print(f"\n  \033[90m{'─'*52}\033[0m")
        print(f"  \033[90mDevice  :\033[0m  {serial}")
        print(f"  \033[90mDisplay :\033[0m  {display_id}")
        print(f"  \033[90mMacro   :\033[0m  {macro.name}  ({len(macro.nodes)} nodes)")
        print(f"  \033[90m{'─'*52}\033[0m")

        confirmed = questionary.confirm(
            "Start macro?",
            default=True,
            style=CLI_STYLE,
        ).ask()

        if not confirmed:
            print("\n  \033[90mCancelled.\033[0m\n")
            sys.exit(0)

        runner = CLIHeadlessRunner(macro, serial, display_id)
        runner.start()

    except KeyboardInterrupt:
        print("\n  \033[90mCancelled.\033[0m\n")
        sys.exit(0)
