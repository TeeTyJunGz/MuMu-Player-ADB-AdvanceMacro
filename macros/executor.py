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
    
    def __init__(self, macro: Macro, device_serial: str):
        self.macro = macro
        self.serial = device_serial
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
            self.pause_event.wait()
    
    def resume(self):
        """Resume from pause"""
        if self.state == "paused":
            self.state = "running"
            self.pause_event.set()
    
    def stop(self):
        """Stop execution"""
        self.stop_event.set()
        self.state = "stopped"
    
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
                
                # Execute node
                result = self._execute_node(node)
                if result.get("success"):
                    self._log("info", f"✅ {node.name}")
                else:
                    err = result.get("error", result.get("reason", "Failed"))
                    self._log("error", f"❌ {node.name} - {err}")
                
                # Determine next node
                if result.get("branch_to"):
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
        max_wait = node.data.get("max_wait_ms", 10000)
        start_time = time.time()
        
        if wait_type == "time":
            self.stop_event.wait(node.data.get("time_ms", 1000) / 1000)
            return {"success": True}
        
        elif wait_type == "pixel":
            pixel_cond = node.data.get("pixel_condition", {})
            while time.time() - start_time < max_wait / 1000:
                if self.stop_event.is_set():
                    break
                if self._check_pixel_color(**pixel_cond):
                    return {"success": True}
                self.stop_event.wait(0.1)
            return {"success": False, "reason": "timeout"}
        
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
        
        if color_id not in self.loop_states:
            self.loop_states[color_id] = {
                "count": 0,
                "start_time": time.time()
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
        if self._check_condition(condition):
            branch = node.data.get("true_branch")
        else:
            branch = node.data.get("false_branch")
        
        return {"success": True, "branch_to": branch}
    
    # Helper methods
    
    def _check_conditions(self, conditions: List[Dict], all_met: bool = True) -> bool:
        """Check if conditions are met"""
        results = [self._check_condition(c) for c in conditions]
        return all(results) if all_met else any(results)
    
    def _check_condition(self, condition: Dict) -> bool:
        """Check single condition"""
        cond_type = condition.get("type")
        
        if cond_type == "color_check":
            return self._check_pixel_color(
                x=condition.get("x"),
                y=condition.get("y"),
                hex_color=condition.get("hex_color"),
                tolerance=condition.get("tolerance_percent", 0)
            )
        
        # TODO: Add time_check, etc.
        return True
    
    def _check_pixel_color(self, x: int, y: int, hex_color: str, tolerance: float = 0) -> bool:
        """Check if pixel at (x,y) matches color (with tolerance)"""
        # TODO: Implement pixel color checking
        return True
    
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
        self.execution_log.append({
            "timestamp": datetime.now().isoformat(),
            "level": level,
            "message": message,
            "node_id": self.current_node_id
        })
        print(f"[MacroExecutor] {level.upper()}: {message}")
