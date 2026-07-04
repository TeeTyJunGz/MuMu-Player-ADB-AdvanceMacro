import time
import threading
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
        self.current_node_id = None
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
    
    def start(self):
        """Start macro execution in background thread"""
        self.state = "running"
        self.pause_event.clear()
        self.stop_event.clear()
        self.execution_log = []
        
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
            visited = set()
            
            while current_id and not self.stop_event.is_set():
                if self.state == "paused":
                    self.pause_event.wait()
                
                if current_id in visited and current_id not in self._get_loop_nodes():
                    # Avoid infinite loops (unless it's a loop node)
                    break
                
                visited.add(current_id)
                self.current_node_id = current_id
                
                node = self.macro.nodes.get(current_id)
                if not node:
                    break
                
                # Execute node
                result = self._execute_node(node)
                self._log("info", f"Executed {node.type}: {node.name} - Result: {result}")
                
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
            elif node.type == "loop":
                result = self._execute_loop(node)
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
        
        # Perform tap
        self.device.shell(f"input tap {x} {y}")
        time.sleep(duration / 1000)
        
        return {"success": True}
    
    def _execute_key(self, node) -> Dict[str, Any]:
        """Execute key input node"""
        text = node.data.get("text_input", "")
        keys = node.data.get("keys", [])
        delay = node.data.get("delay_between_keys_ms", 50)
        
        if text:
            self.device.shell(f"input text '{text}'")
        
        for key in keys:
            self.device.shell(f"input keyevent {self._key_to_keycode(key)}")
            time.sleep(delay / 1000)
        
        return {"success": True}
    
    def _execute_wait(self, node) -> Dict[str, Any]:
        """Execute wait node"""
        wait_type = node.data.get("wait_type", "time")
        max_wait = node.data.get("max_wait_ms", 10000)
        start_time = time.time()
        
        if wait_type == "time":
            time.sleep(node.data.get("time_ms", 1000) / 1000)
            return {"success": True}
        
        elif wait_type == "pixel":
            pixel_cond = node.data.get("pixel_condition", {})
            while time.time() - start_time < max_wait / 1000:
                if self._check_pixel_color(**pixel_cond):
                    return {"success": True}
                time.sleep(0.1)
            return {"success": False, "reason": "timeout"}
        
        return {"success": True}
    
    def _execute_delay(self, node) -> Dict[str, Any]:
        """Execute delay node"""
        delay_ms = node.data.get("delay_ms", 1000)
        time.sleep(delay_ms / 1000)
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
    
    def _execute_loop(self, node) -> Dict[str, Any]:
        """Execute loop node"""
        loop_type = node.data.get("loop_type", "fixed_count")
        iterations = node.data.get("iterations", 1)
        
        for i in range(iterations):
            if self.stop_event.is_set():
                break
            # Execute loop body
            body_nodes = node.data.get("body_nodes", [])
            # TODO: implement loop logic
        
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
        return [n_id for n_id, n in self.macro.nodes.items() if n.type == "loop"]
    
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
