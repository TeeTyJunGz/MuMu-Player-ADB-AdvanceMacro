import time
import threading
import random
from typing import Optional, Dict, Any, List
from datetime import datetime
import adbutils
from PIL import Image, ImageDraw
import io
import logging

from .models import Macro, NodeType, WaitType
from .storage import MacroStorage

logger = logging.getLogger(__name__)

class MacroExecutor:
    """Executes macro workflows"""
    
    def __init__(self, macro: Macro, device_serial: str, get_frame_callback=None):
        self.macro = macro
        self.serial = device_serial
        self.get_frame_callback = get_frame_callback
        self.adb = adbutils.AdbClient(host="127.0.0.1", port=5037)
        self.device = self.adb.device(device_serial)
        
        self.state = "idle"  # idle, running, paused, stopped
        self.execution_log = []
        self.loop_states = {} # track iterations and start times per loop color id
        
        self.stop_event = threading.Event()
        self.pause_event = threading.Event()
        
    def start(self):
        """Start macro execution in background thread"""
        self.state = "running"
        self.pause_event.clear()
        self.stop_event.clear()
        self.execution_log = []
        self.loop_states = {}
        
        thread = threading.Thread(target=self._execute, daemon=True)
        thread.start()
        return thread
    
    def pause(self):
        """Pause execution"""
        if self.state == "running":
            self.state = "paused"
            self.pause_event.clear()
    
    def resume(self):
        """Resume from pause"""
        if self.state == "paused":
            self.state = "running"
            self.pause_event.set()
    
    def stop(self):
        """Stop execution"""
        self.stop_event.set()
        self.state = "stopped"
        # Unblock if paused
        self.pause_event.set()
    
    def _execute(self):
        """Main execution loop"""
        try:
            # Find start node (first node with no incoming connections)
            start_nodes = self._find_start_nodes()
            if not start_nodes:
                self._log("error", "No start node found")
                return
            
            current_id = start_nodes[0]
            while current_id and not self.stop_event.is_set():
                if self.state == "paused":
                    self.pause_event.wait()
                
                self.current_node_id = current_id
                
                node = self.macro.nodes.get(current_id)
                if not node:
                    break
                
                # Log when operation starts
                self._log("info", f"✅ {node.name}")
                
                # Execute node
                result = self._execute_node(node)
                
                if self.stop_event.is_set():
                    self._log("error", f"❌ {node.name} - stopped")
                    break
                
                if not result.get("success"):
                    err = result.get("error", result.get("reason", "Failed"))
                    self._log("error", f"❌ {node.name} - {err}")
                
                # Determine next node
                if "branch_to" in result:
                    current_id = result["branch_to"]
                else:
                    next_nodes = self.macro.get_next_nodes(current_id)
                    current_id = next_nodes[0] if next_nodes else None
            
            self.state = "stopped"
            self._log("info", "Macro execution completed")
        
        except Exception as e:
            self._log("error", f"Execution error: {e}")
            self.state = "stopped"
    
    def _execute_node(self, node) -> Dict[str, Any]:
        """Execute single node, return result"""
        result = {"success": False}
        
        try:
            disabled = node.data.get("disabled") or node.data.get("data", {}).get("disabled")
            if disabled:
                if node.type == "condition":
                    next_nodes = self.macro.get_next_nodes(node.id, label="true")
                    branch = next_nodes[0] if next_nodes else None
                    return {"success": True, "branch_to": branch}
                elif node.type not in ("loop_start", "loop_end"):
                    return {"success": True}
                    
            if node.type == "tap":
                result = self._execute_tap(node)
            elif node.type == "key":
                result = self._execute_key(node)
            elif node.type == "wait":
                result = self._execute_wait(node)
            elif node.type == "ocr":
                result = self._execute_ocr(node)
            elif node.type == "screenshot":
                result = self._execute_screenshot(node)
            elif node.type == "delay":
                result = self._execute_delay(node)
            elif node.type == "loop_start":
                result = self._execute_loop_start(node)
            elif node.type == "loop_end":
                result = self._execute_loop_end(node)
            elif node.type == "condition":
                result = self._execute_condition(node)
        
        except Exception as e:
            self._log("error", f"Node error ({node.type}): {e}")
            result["error"] = str(e)
        
        return result
    
    def _execute_tap(self, node) -> Dict[str, Any]:
        """Execute tap node"""
        x = node.data.get("x", 0)
        y = node.data.get("y", 0)
        duration = node.data.get("duration_ms", 50)
        
        # Check conditions
        conditions = node.data.get("conditions", [])
        if conditions:
            all_met = node.data.get("execute_if_all_conditions_met", True)
            if not self._check_conditions(conditions, all_met):
                return {"success": False, "skipped": True}
        
        # Apply Randomization
        if node.data.get("randomize"):
            rand_x = node.data.get("rand_x", 2)
            rand_y = node.data.get("rand_y", 2)
            dmin = node.data.get("rand_dur_min", 20)
            dmax = node.data.get("rand_dur_max", 80)
            pmin = node.data.get("rand_predelay_min", 0)
            pmax = node.data.get("rand_predelay_max", 50)
            
            # Pre-delay
            predelay = random.randint(min(pmin, pmax), max(pmin, pmax))
            if predelay > 0:
                if self.stop_event.wait(predelay / 1000):
                    return {"success": False, "error": "Stopped"}
            
            x += random.randint(-rand_x, rand_x)
            y += random.randint(-rand_y, rand_y)
            # Ensure coordinates don't go negative
            x = max(0, x)
            y = max(0, y)
            
            duration = random.randint(min(dmin, dmax), max(dmin, dmax))
        
        # Perform tap
        self.device.shell(f"input tap {x} {y}")
        self.stop_event.wait(duration / 1000)
        
        return {"success": True}
    
    def _execute_key(self, node) -> Dict[str, Any]:
        """Execute key input node"""
        text = node.data.get("text_input", "")
        keys = node.data.get("keys", [])
        delay = node.data.get("delay_between_keys_ms", 50)
        
        if text:
            self.device.shell(f"input text '{text}'")
        
        for key in keys:
            if self.stop_event.is_set():
                break
            self.device.shell(f"input keyevent {self._key_to_keycode(key)}")
            self.stop_event.wait(delay / 1000)
        
        return {"success": True}
    
    def _execute_wait(self, node) -> Dict[str, Any]:
        """Execute wait node"""
        wait_type = node.data.get("wait_type", "time")
        max_wait = node.data.get("max_wait_ms", 0)  # 0 = infinite
        start_time = time.time()
        
        if wait_type == "time":
            wait_ms = node.data.get("time_ms", 1000)
            if wait_ms <= 0:
                # Infinite wait — just wait for stop signal
                self.stop_event.wait()
            else:
                self.stop_event.wait(wait_ms / 1000)
            return {"success": True}
        
        elif wait_type in ("pixel", "time_or_pixel"):
            pixel_cond = node.data.get("pixel_condition", {})
            # Extract args explicitly to avoid passing unknown kwargs
            px = pixel_cond.get("x", 0)
            py = pixel_cond.get("y", 0)
            hex_c = pixel_cond.get("hex_color", "#000000")
            tol = pixel_cond.get("tolerance_percent", 10)
            
            # For 'time_or_pixel', use time_ms as the max wait time, otherwise use max_wait_ms
            wait_limit = node.data.get("time_ms", 1000) if wait_type == "time_or_pixel" else max_wait
            
            while True:
                if self.stop_event.is_set():
                    return {"success": False, "reason": "stopped"}
                if self._check_pixel_color(x=px, y=py, hex_color=hex_c, tolerance=tol):
                    return {"success": True}
                # Check timeout (0 = infinite)
                if wait_limit > 0 and (time.time() - start_time) >= wait_limit / 1000:
                    # If time_or_pixel, timing out is considered success (we waited the full time)
                    if wait_type == "time_or_pixel":
                        return {"success": True}
                    return {"success": False, "reason": "timeout"}
                self.stop_event.wait(0.1)
        
        return {"success": True}
    
    def _execute_delay(self, node) -> Dict[str, Any]:
        """Execute delay node"""
        delay_ms = node.data.get("delay_ms", 1000)
        self.stop_event.wait(delay_ms / 1000)
        return {"success": True}
    
    def _execute_screenshot(self, node) -> Dict[str, Any]:
        """Capture screenshot"""
        filename = node.data.get("save_filename", f"screenshot_{datetime.now().timestamp()}.png")
        # TODO: capture screen and save
        return {"success": True, "filename": filename}
    
    def _execute_ocr(self, node) -> Dict[str, Any]:
        """Execute OCR node"""
        # TODO: Implement OCR if tesseract available
        return {"success": True, "text": ""}
    
    def _execute_loop_start(self, node) -> Dict[str, Any]:
        """Execute loop start node"""
        color_id = node.data.get("loop_color_id", 0)
        
        # Always reset loop state when entering loop_start to allow safe re-entry
        self.loop_states[color_id] = {
            "count": 0,
            "start_time": time.time(),
            "loop_type": node.data.get("loop_type", "fixed_count"),
            "iterations": int(node.data.get("iterations", 1))
        }
        
        # Loop start doesn't evaluate condition to jump OUT of loop, 
        # it just initializes and passes execution inside. 
        # The loop end evaluates whether to repeat or exit.
        return {"success": True}
        
    def _execute_loop_end(self, node) -> Dict[str, Any]:
        """Execute loop end node"""
        color_id = node.data.get("loop_color_id", 0)
        
        # Find matching loop_start node to check conditions
        start_node = next((n for n in self.macro.nodes.values() 
                           if n.type == "loop_start" and n.data.get("loop_color_id", 0) == color_id), None)
                           
        if not start_node:
            return {"success": False, "error": "Missing corresponding Loop Start node for this color"}
            
        state = self.loop_states.get(color_id, {"count": 0, "start_time": time.time()})
        state["count"] += 1
        
        loop_type = start_node.data.get("loop_type", "fixed_count")
        should_continue = False
        
        if loop_type == "fixed_count":
            iterations = int(start_node.data.get("iterations", 1))
            should_continue = state["count"] < iterations
        elif loop_type == "while_true":
            should_continue = True
        elif loop_type == "until_time":
            stop_time_str = start_node.data.get("stop_time", "00:00")
            try:
                now = datetime.now()
                stop_h, stop_m = map(int, stop_time_str.split(":"))
                stop_time = now.replace(hour=stop_h, minute=stop_m, second=0, microsecond=0)
                # If stop time is earlier today, assume it meant tomorrow
                if stop_time < now:
                    stop_time = stop_time.replace(day=stop_time.day + 1)
                should_continue = now < stop_time
            except:
                should_continue = False # invalid time format, exit loop
        elif loop_type == "until_color":
            # Check if pixel has matched the color, if so, exit. Otherwise continue.
            px = int(start_node.data.get("pixel_x", 0))
            py = int(start_node.data.get("pixel_y", 0))
            phex = start_node.data.get("pixel_hex", "#000000")
            matched = self._check_pixel_color(px, py, phex)
            should_continue = not matched
            
        if should_continue:
            # Branch back to the node following loop_start (loop body)
            # Default branch from start_node is the loop body
            next_nodes = self.macro.get_next_nodes(start_node.id)
            if next_nodes:
                return {"success": True, "branch_to": next_nodes[0]}
            else:
                return {"success": True} # Nowhere to branch to
        else:
            # Loop satisfied, clear state and exit out of loop_end output
            if color_id in self.loop_states:
                del self.loop_states[color_id]
            # Will automatically flow to the next node connected to this loop_end
            return {"success": True}
            
    def _execute_condition(self, node) -> Dict[str, Any]:
        """Execute condition branching"""
        condition = node.data.get("condition", {})
        branch_label = "true" if self._check_condition(condition) else "false"
        
        next_nodes = self.macro.get_next_nodes(node.id, label=branch_label)
        branch = next_nodes[0] if next_nodes else None
        
        return {"success": True, "branch_to": branch}
    
    # Helper methods
    
    def _check_conditions(self, conditions: List[Dict], all_met: bool = True) -> bool:
        """Check if conditions are met"""
        results = [self._check_condition(c) for c in conditions]
        return all(results) if all_met else any(results)
    
    def _check_condition(self, condition: Dict) -> bool:
        """Check single condition"""
        cond_type = condition.get("type")
        
        if cond_type == "color_check" or cond_type == "pixel_color":
            return self._check_pixel_color(
                x=condition.get("x"),
                y=condition.get("y"),
                hex_color=condition.get("hex_color", "#000000"),
                tolerance=condition.get("tolerance_percent", 10)
            )
        
        # TODO: Add time_check, etc.
        return True
    
    def _check_pixel_color(self, x: int, y: int, hex_color: str, tolerance: float = 10) -> bool:
        """Check if pixel at (x,y) matches color (with tolerance)"""
        frame = self.get_frame_callback() if self.get_frame_callback else None
        
        try:
            if frame is None:
                # Fallback to ADB screenshot (headless mode)
                pil_img = self.device.screenshot()
                if pil_img is None:
                    return False
                w, h = pil_img.size
                px = max(0, min(int(x), w - 1))
                py = max(0, min(int(y), h - 1))
                r, g, b = pil_img.getpixel((px, py))[:3]
            else:
                # frame is a numpy array (BGR format typically from OpenCV)
                h, w = frame.shape[:2]
                
                # Ensure coordinates are within bounds
                py = max(0, min(int(y), h - 1))
                px = max(0, min(int(x), w - 1))
                
                # OpenCV frame is BGR
                b, g, r = frame[py, px][:3]
                b, g, r = int(b), int(g), int(r)
            
            # Parse target hex color
            hex_color = hex_color.lstrip('#')
            if len(hex_color) == 6:
                target_r = int(hex_color[0:2], 16)
                target_g = int(hex_color[2:4], 16)
                target_b = int(hex_color[4:6], 16)
            else:
                return False
                
            # Calculate difference (Manhattan distance / max possible distance)
            diff = abs(r - target_r) + abs(g - target_g) + abs(b - target_b)
            diff_percent = (diff / 765.0) * 100.0
            
            return diff_percent <= tolerance
            
        except Exception as e:
            self._log("error", f"Pixel check failed: {str(e)}")
            return False
    
    def _find_start_nodes(self) -> List[str]:
        """Find nodes with no incoming connections"""
        incoming = set()
        for conn in self.macro.connections:
            incoming.add(conn.to_id)
        
        return [n_id for n_id in self.macro.nodes.keys() if n_id not in incoming]
    
    def _get_loop_nodes(self) -> List[str]:
        """Get IDs of all loop nodes"""
        return [n_id for n_id, n in self.macro.nodes.items() if n.type in ("loop_start", "loop_end")]
    
    def _key_to_keycode(self, key: str) -> int:
        """Convert key name to Android keycode"""
        keycodes = {
            "enter": 66, "escape": 111, "backspace": 67, "delete": 112,
            "tab": 61, "space": 62, "a": 29, "b": 30, "c": 31,
            # Add more as needed
        }
        return keycodes.get(key.lower(), 0)
    
    def _log(self, level: str, message: str):
        """Log execution event"""
        prefix = ""
        if self.loop_states:
            # find oldest active loop (outermost)
            outermost = min(self.loop_states.values(), key=lambda x: x["start_time"])
            ltype = outermost.get("loop_type")
            if ltype == "fixed_count":
                prefix = f"[Loop {outermost.get('count', 0)+1}/{outermost.get('iterations', 1)}] "
            elif ltype == "while_true":
                prefix = "[Loop ∞] "
            elif ltype == "until_time":
                prefix = "[Loop 🕒] "
            elif ltype == "until_color":
                prefix = "[Loop 🎨] "
            else:
                prefix = "[Loop] "
                
        full_message = f"{prefix}{message}"
        
        self.execution_log.append({
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": full_message,
            "node_id": self.current_node_id
        })
        print(f"[MacroExecutor] {level.upper()}: {full_message}")
