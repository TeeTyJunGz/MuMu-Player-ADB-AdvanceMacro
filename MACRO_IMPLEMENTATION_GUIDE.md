# Macro System Implementation Guide

This guide tells you (another AI) exactly what to do to implement the macro system. Follow this step-by-step.

---

## Quick Start (TL;DR)

1. Read `MACRO_SYSTEM_SPECIFICATION.md` completely
2. Implement backend (models, storage, executor) - **DO FIRST**
3. Add macro API endpoints to Flask app
4. Build recording mode UI (tap capture + action history)
5. Build visual editor UI (node graph)
6. Test each component before moving to next

---

## Prerequisites

**Files to examine before starting:**
- `app.py` - Flask backend structure
- `templates/index.html` - Frontend structure
- `requirements.txt` - Python dependencies

**New dependencies to add:**
```
pytesseract>=0.3.10          # For OCR (optional but recommended)
pillow>=9.0.0                # Already in requirements
numpy>=1.0                   # Already in requirements
```

For tesseract, install system binary first:
- Windows: `choco install tesseract` or download installer
- Mac: `brew install tesseract`
- Linux: `apt-get install tesseract-ocr`

---

## Phase 1: Backend Implementation

### Step 1.1: Create Macro Models

**File:** `macros/models.py` (NEW)

Create these Python classes:

```python
import json
from typing import Dict, List, Any, Optional
from enum import Enum
from datetime import datetime
import uuid

class NodeType(Enum):
    TAP = "tap"
    KEY = "key"
    WAIT = "wait"
    OCR = "ocr"
    LOOP = "loop"
    CONDITION = "condition"
    SCREENSHOT = "screenshot"
    DELAY = "delay"

class WaitType(Enum):
    TIME = "time"
    PIXEL = "pixel"
    TIME_OR_PIXEL = "time_or_pixel"
    ANY_PIXEL_CHANGE = "any_pixel_change"

class LoopType(Enum):
    FIXED_COUNT = "fixed_count"
    WHILE_TRUE = "while_true"
    UNTIL_COLOR = "until_color"

# Node classes
class Condition:
    """Single condition (color check, time check, etc.)"""
    def __init__(self, type_: str, **kwargs):
        self.type = type_
        self.data = kwargs
    
    def to_dict(self):
        return {"type": self.type, **self.data}

class MacroNode:
    """Single node in macro workflow"""
    def __init__(self, node_id: str, node_type: str, name: str = "", **data):
        self.id = node_id
        self.type = node_type
        self.name = name
        self.data = data  # Type-specific data (x, y, iterations, etc.)
    
    def to_dict(self):
        return {
            "id": self.id,
            "type": self.type,
            "name": self.name,
            **self.data
        }
    
    @staticmethod
    def from_dict(d):
        node_id = d.pop("id")
        node_type = d.pop("type")
        name = d.pop("name", "")
        return MacroNode(node_id, node_type, name, **d)

class Connection:
    """Connection between two nodes"""
    def __init__(self, from_id: str, to_id: str, label: str = "default"):
        self.from_id = from_id
        self.to_id = to_id
        self.label = label
    
    def to_dict(self):
        return {"from": self.from_id, "to": self.to_id, "label": self.label}

class Macro:
    """Complete macro workflow"""
    def __init__(self, macro_id: str, name: str, description: str = ""):
        self.id = macro_id or f"macro_{int(datetime.now().timestamp() * 1000)}"
        self.name = name
        self.description = description
        self.created_at = datetime.now().isoformat()
        self.modified_at = datetime.now().isoformat()
        self.nodes: Dict[str, MacroNode] = {}
        self.connections: List[Connection] = []
    
    def add_node(self, node: MacroNode):
        """Add node to macro"""
        self.nodes[node.id] = node
        self.modified_at = datetime.now().isoformat()
    
    def add_connection(self, connection: Connection):
        """Add connection between nodes"""
        self.connections.append(connection)
        self.modified_at = datetime.now().isoformat()
    
    def get_next_nodes(self, node_id: str, label: str = "default") -> List[str]:
        """Get IDs of nodes that follow given node"""
        return [c.to_id for c in self.connections if c.from_id == node_id and c.label == label]
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize macro to dict"""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "modified_at": self.modified_at,
            "nodes": [n.to_dict() for n in self.nodes.values()],
            "connections": [c.to_dict() for c in self.connections]
        }
    
    @staticmethod
    def from_dict(d: Dict) -> "Macro":
        """Deserialize macro from dict"""
        macro = Macro(d.get("id"), d.get("name", ""), d.get("description", ""))
        macro.created_at = d.get("created_at", macro.created_at)
        macro.modified_at = d.get("modified_at", macro.modified_at)
        
        for node_data in d.get("nodes", []):
            node = MacroNode.from_dict(node_data.copy())
            macro.nodes[node.id] = node
        
        for conn_data in d.get("connections", []):
            conn = Connection(conn_data["from"], conn_data["to"], 
                            conn_data.get("label", "default"))
            macro.connections.append(conn)
        
        return macro
```

### Step 1.2: Create Macro Storage

**File:** `macros/storage.py` (NEW)

```python
import json
import os
from typing import Optional, List
from .models import Macro

MACROS_DIR = "macros_data"  # Directory to store .macro.json files

class MacroStorage:
    """Save and load macros from JSON files"""
    
    @staticmethod
    def ensure_dir():
        os.makedirs(MACROS_DIR, exist_ok=True)
    
    @staticmethod
    def get_path(macro_id: str) -> str:
        return os.path.join(MACROS_DIR, f"{macro_id}.macro.json")
    
    @staticmethod
    def save(macro: Macro):
        """Save macro to disk"""
        MacroStorage.ensure_dir()
        path = MacroStorage.get_path(macro.id)
        with open(path, 'w') as f:
            json.dump(macro.to_dict(), f, indent=2)
        print(f"[MacroStorage] Saved macro: {macro.id}")
    
    @staticmethod
    def load(macro_id: str) -> Optional[Macro]:
        """Load macro from disk"""
        path = MacroStorage.get_path(macro_id)
        if not os.path.exists(path):
            return None
        with open(path, 'r') as f:
            data = json.load(f)
        return Macro.from_dict(data)
    
    @staticmethod
    def list_all() -> List[str]:
        """List all macro IDs"""
        MacroStorage.ensure_dir()
        files = os.listdir(MACROS_DIR)
        return [f.replace(".macro.json", "") for f in files if f.endswith(".macro.json")]
    
    @staticmethod
    def delete(macro_id: str):
        """Delete macro"""
        path = MacroStorage.get_path(macro_id)
        if os.path.exists(path):
            os.remove(path)
            print(f"[MacroStorage] Deleted macro: {macro_id}")
```

### Step 1.3: Create Macro Executor

**File:** `macros/executor.py` (NEW)

This is the core logic that executes macros step-by-step:

```python
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
        self.device = self.adb.device(serial)
        
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
```

### Step 1.4: Add Flask API Endpoints

**File:** `app.py` - Add these routes:

```python
from macros.models import Macro, MacroNode, Connection
from macros.storage import MacroStorage
from macros.executor import MacroExecutor

# Global executor reference
current_executor = None

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
        
        current_executor = MacroExecutor(macro, serial)
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
    """Get pixel color at coordinates"""
    try:
        data = request.json or {}
        x, y = data.get("x"), data.get("y")
        
        if x is None or y is None:
            return jsonify({"ok": False, "error": "x, y required"}), 400
        
        # TODO: Capture screen and get pixel color
        # For now, return mock data
        return jsonify({
            "ok": True,
            "x": x,
            "y": y,
            "hex": "#FF5733",
            "rgb": (255, 87, 51)
        })
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500
```

---

## Phase 2: Frontend Implementation

(Continue in next section due to length)

### Step 2.1: Create Macro Panel HTML

**File:** `templates/macro_panel.html` (NEW)

```html
<div id="macro-panel" style="display: none;">
  <!-- Macro list -->
  <div id="macro-list-container">
    <h3>Macros</h3>
    <button id="btn-new-macro">+ New Macro</button>
    <div id="macro-list" style="border: 1px solid #ccc; height: 200px; overflow-y: auto;"></div>
  </div>
  
  <!-- Macro editor -->
  <div id="macro-editor" style="display: none;">
    <h3>Edit Macro</h3>
    <input type="text" id="macro-name" placeholder="Macro name">
    <textarea id="macro-description" placeholder="Description"></textarea>
    
    <!-- Node graph canvas -->
    <div id="node-graph-canvas" style="border: 1px solid #333; height: 400px; background: #f9f9f9;"></div>
    
    <!-- Playback controls -->
    <div style="margin-top: 20px;">
      <button id="btn-macro-play">▶ Play</button>
      <button id="btn-macro-pause">⏸ Pause</button>
      <button id="btn-macro-stop">⏹ Stop</button>
    </div>
    
    <!-- Execution log -->
    <div id="macro-log" style="border: 1px solid #ccc; height: 150px; overflow-y: auto; margin-top: 10px; font-size: 12px;">
      <pre id="log-content"></pre>
    </div>
  </div>
</div>
```

### Step 2.2: Create Recording Mode UI

**File:** `templates/macro_recorder.html` (NEW)

```html
<div id="recording-panel" style="display: none; position: fixed; top: 10px; right: 10px; background: white; border: 2px solid red; padding: 10px; z-index: 9999;">
  <h3>🔴 Recording Macro</h3>
  <p>Tap on the screen to record coordinates</p>
  
  <div id="recording-actions" style="max-height: 300px; overflow-y: auto;">
    <!-- Actions will be added here -->
  </div>
  
  <div style="margin-top: 10px;">
    <button id="btn-add-delay">+ Delay</button>
    <button id="btn-add-wait">+ Wait</button>
    <button id="btn-add-key">+ Key</button>
    <button id="btn-finish-recording">✓ Finish</button>
    <button id="btn-cancel-recording">✕ Cancel</button>
  </div>
</div>
```

---

## Phase 3: Testing Checklist

After implementation, test:

- [ ] Create macro with name
- [ ] Add tap node with coordinates
- [ ] Add key input node
- [ ] Add delay node
- [ ] Connect nodes in workflow
- [ ] Play macro (should execute nodes in sequence)
- [ ] Pause and resume
- [ ] Stop mid-execution
- [ ] Load/save macro from disk
- [ ] List all macros
- [ ] Delete macro

---

## Common Pitfalls to Avoid

1. **Don't hardcode display logic** - Keep UI separate from executor
2. **Don't skip node ID validation** - Ensure connections reference valid nodes
3. **Don't execute OCR without checking** - It's optional/slow
4. **Don't forget file permissions** - `macros_data/` directory must be writable
5. **Don't block UI during execution** - Always run executor in background thread
6. **Don't lose execution logs** - Keep them for debugging

---

## How Other AIs Should Use This Guide

1. Read the `MACRO_SYSTEM_SPECIFICATION.md` first
2. Implement Phase 1 (backend) completely before UI
3. Test backend endpoints with curl/Postman before frontend
4. Use this checklist to track progress
5. For questions, refer back to the spec document
6. Save all changes to `app.py` and new files (don't lose them!)

---

## Questions to Ask Yourself

- ✅ Do all node types serialize/deserialize correctly?
- ✅ Does executor handle branches (conditions, loops)?
- ✅ Can I load a saved macro and replay it identically?
- ✅ Is the execution log useful for debugging?
- ✅ Does the UI feel responsive (no freezing)?
- ✅ Can users easily add/remove/reorder nodes?

If you answer NO to any, go back and fix it before moving on.
