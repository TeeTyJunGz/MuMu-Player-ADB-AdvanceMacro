# Macro System Code Examples

Complete, copy-paste-ready code snippets for implementing the macro system.

---

## Creating Your First Macro (Python)

```python
from macros.models import Macro, MacroNode, Connection
from macros.storage import MacroStorage

# Create macro
macro = Macro(None, "Login Test", "Logs into the app")

# Create nodes
tap_email = MacroNode("n1", "tap", "Tap Email Field", 
                      x=200, y=300, duration_ms=50)
key_email = MacroNode("n2", "key", "Type Email",
                      text_input="user@example.com", delay_between_keys_ms=50)
tap_pass = MacroNode("n3", "tap", "Tap Password Field",
                     x=200, y=350, duration_ms=50)
key_pass = MacroNode("n4", "key", "Type Password",
                     text_input="password123", delay_between_keys_ms=50)
tap_login = MacroNode("n5", "tap", "Tap Login",
                      x=640, y=500, duration_ms=50,
                      conditions=[{
                          "type": "color_check",
                          "x": 640,
                          "y": 500,
                          "hex_color": "#2196F3",
                          "tolerance_percent": 10
                      }])

# Add nodes
macro.add_node(tap_email)
macro.add_node(key_email)
macro.add_node(tap_pass)
macro.add_node(key_pass)
macro.add_node(tap_login)

# Connect nodes
macro.add_connection(Connection("n1", "n2"))  # tap_email → key_email
macro.add_connection(Connection("n2", "n3"))  # key_email → tap_pass
macro.add_connection(Connection("n3", "n4"))  # tap_pass → key_pass
macro.add_connection(Connection("n4", "n5"))  # key_pass → tap_login

# Save
MacroStorage.save(macro)
print(f"Macro saved with ID: {macro.id}")
```

---

## Reading a Saved Macro

```python
from macros.storage import MacroStorage

# List all macros
all_macros = MacroStorage.list_all()
print(f"Found {len(all_macros)} macros: {all_macros}")

# Load specific macro
macro_id = all_macros[0] if all_macros else None
if macro_id:
    macro = MacroStorage.load(macro_id)
    print(f"Loaded: {macro.name}")
    print(f"Nodes: {len(macro.nodes)}")
    print(f"Connections: {len(macro.connections)}")
    
    # Inspect nodes
    for node_id, node in macro.nodes.items():
        print(f"  {node_id}: {node.type} - {node.name}")
```

---

## Executing a Macro

```python
from macros.storage import MacroStorage
from macros.executor import MacroExecutor
import time

# Load macro
macro = MacroStorage.load("macro_1720058788123")

# Create executor
executor = MacroExecutor(macro, "192.168.1.152:5555")

# Start execution in background
thread = executor.start()

# Wait for completion
thread.join(timeout=30)

# Check results
print(f"Final state: {executor.state}")
print(f"Execution log entries: {len(executor.execution_log)}")

# Print log
for entry in executor.execution_log:
    print(f"[{entry['timestamp']}] {entry['level']}: {entry['message']}")
```

---

## Creating Macro with Wait Node

```python
from macros.models import MacroNode

# Wait 3 seconds
wait_3s = MacroNode("n_wait1", "wait", "Wait 3 seconds",
                    wait_type="time", time_ms=3000)

# Wait for pixel to turn green
wait_green = MacroNode("n_wait2", "wait", "Wait for success indicator",
                       wait_type="pixel",
                       pixel_condition={
                           "x": 640,
                           "y": 100,
                           "hex_color": "#4CAF50"
                       },
                       max_wait_ms=5000)

# Wait for EITHER time OR pixel (whichever comes first)
wait_combo = MacroNode("n_wait3", "wait", "Wait for response",
                       wait_type="time_or_pixel",
                       time_ms=2000,
                       pixel_condition={
                           "x": 400,
                           "y": 400,
                           "hex_color": "#FF0000"
                       },
                       max_wait_ms=5000)
```

---

## Creating Loop Node

```python
from macros.models import MacroNode

# Simple loop: repeat 5 times
loop_5x = MacroNode("loop1", "loop", "Repeat 5 times",
                    loop_type="fixed_count",
                    iterations=5,
                    body_nodes=["n1", "n2", "n3"],
                    delay_between_iterations_ms=500)

# Loop until button becomes red (with max iterations)
loop_until = MacroNode("loop2", "loop", "Keep tapping until red",
                       loop_type="while_true",
                       iterations=999,  # safety max
                       body_nodes=["tap_node"],
                       break_condition={
                           "type": "pixel_color",
                           "x": 640,
                           "y": 500,
                           "hex_color": "#FF0000",
                           "tolerance_percent": 5
                       })
```

---

## Creating Conditional Node

```python
from macros.models import MacroNode

# Branch based on pixel color
condition = MacroNode("cond1", "condition", "Is button blue?",
                      condition={
                          "type": "pixel_color",
                          "x": 640,
                          "y": 500,
                          "hex_color": "#2196F3",
                          "tolerance_percent": 10
                      },
                      true_branch="tap_button_node",
                      false_branch="wait_loading_node")

# Workflow:
# If button is blue → tap it
# If button is not blue → wait for it to load
```

---

## Flask API Usage Examples

### Create Macro via API

```bash
curl -X POST http://127.0.0.1:5000/api/macros \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My First Macro",
    "description": "Test macro"
  }'

# Response:
# {
#   "ok": true,
#   "macro": {
#     "id": "macro_1720058788123",
#     "name": "My First Macro",
#     "nodes": [],
#     "connections": []
#   }
# }
```

### Update Macro via API

```bash
curl -X PUT http://127.0.0.1:5000/api/macros/macro_1720058788123 \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Updated Name",
    "nodes": [
      {
        "id": "n1",
        "type": "tap",
        "name": "Tap Button",
        "x": 640,
        "y": 720
      }
    ],
    "connections": []
  }'
```

### Play Macro via API

```bash
curl -X POST http://127.0.0.1:5000/api/macros/macro_1720058788123/play \
  -H "Content-Type: application/json" \
  -d '{"serial": "192.168.1.152:5555"}'
```

### Get Execution Status

```bash
curl http://127.0.0.1:5000/api/macros/macro_1720058788123/status

# Response:
# {
#   "ok": true,
#   "status": "running",
#   "current_node": "n1",
#   "log": [
#     {
#       "timestamp": "2026-07-04T03:46:28.123Z",
#       "level": "info",
#       "message": "Executed tap: Tap Button",
#       "node_id": "n1"
#     }
#   ]
# }
```

---

## JavaScript Frontend Examples

### Load and Display Macros

```javascript
async function loadMacros() {
  try {
    const response = await fetch('/api/macros');
    const data = await response.json();
    
    if (data.ok) {
      const macros = data.macros;
      console.log(`Found ${macros.length} macros`);
      
      // Display macro list
      const list = document.getElementById('macro-list');
      list.innerHTML = macros.map(m => `
        <div class="macro-item">
          <strong>${m.name}</strong>
          <p>${m.description}</p>
          <p>Nodes: ${m.node_count} | Created: ${m.created_at}</p>
          <button onclick="editMacro('${m.id}')">Edit</button>
          <button onclick="playMacro('${m.id}')">Play</button>
          <button onclick="deleteMacro('${m.id}')">Delete</button>
        </div>
      `).join('');
    }
  } catch (error) {
    console.error('Error loading macros:', error);
  }
}
```

### Create New Macro

```javascript
async function createMacro() {
  const name = prompt('Macro name:');
  const description = prompt('Description:');
  
  if (!name) return;
  
  try {
    const response = await fetch('/api/macros', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, description})
    });
    
    const data = await response.json();
    if (data.ok) {
      console.log('Macro created:', data.macro.id);
      loadMacros();  // Refresh list
      editMacro(data.macro.id);  // Open editor
    }
  } catch (error) {
    console.error('Error creating macro:', error);
  }
}
```

### Play Macro

```javascript
async function playMacro(macroId) {
  const serial = await getConnectedDevice();
  if (!serial) {
    alert('No device connected');
    return;
  }
  
  try {
    const response = await fetch(`/api/macros/${macroId}/play`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({serial})
    });
    
    const data = await response.json();
    if (data.ok) {
      console.log('Macro started');
      
      // Poll for status
      const statusInterval = setInterval(async () => {
        const statusResp = await fetch(`/api/macros/${macroId}/status`);
        const statusData = await statusResp.json();
        
        if (statusData.ok) {
          updateExecutionLog(statusData.log);
          
          if (statusData.status === 'stopped') {
            clearInterval(statusInterval);
            console.log('Macro finished');
          }
        }
      }, 500);
    }
  } catch (error) {
    console.error('Error playing macro:', error);
  }
}
```

### Update Execution Log

```javascript
function updateExecutionLog(logEntries) {
  const logContent = document.getElementById('log-content');
  const html = logEntries.map(entry => `
    <div class="log-entry ${entry.level}">
      <span class="time">${new Date(entry.timestamp).toLocaleTimeString()}</span>
      <span class="level">[${entry.level.toUpperCase()}]</span>
      <span class="message">${entry.message}</span>
      <span class="node">${entry.node_id}</span>
    </div>
  `).join('');
  
  logContent.innerHTML = html;
  logContent.scrollTop = logContent.scrollHeight;  // Auto-scroll to bottom
}
```

---

## Recording Mode Example (Frontend)

```javascript
let recordingMode = false;
let recordingMacro = null;
let recordingNodes = [];

// Start recording
function startRecording() {
  recordingMode = true;
  recordingNodes = [];
  recordingMacro = {
    id: `macro_${Date.now()}`,
    name: prompt('Macro name:'),
    nodes: [],
    connections: []
  };
  
  // Show recording overlay
  document.getElementById('recording-panel').style.display = 'block';
  
  // Enable tap detection on video stream
  setupTapDetection();
}

// Detect tap and record coordinates
function setupTapDetection() {
  const videoElement = document.getElementById('video-stream');
  
  videoElement.addEventListener('click', (e) => {
    if (!recordingMode) return;
    
    const rect = videoElement.getBoundingClientRect();
    const x = Math.round((e.clientX - rect.left) * (videoElement.videoWidth / rect.width));
    const y = Math.round((e.clientY - rect.top) * (videoElement.videoHeight / rect.height));
    
    // Add tap node
    const nodeId = `tap_${recordingNodes.length}`;
    const node = {
      id: nodeId,
      type: 'tap',
      name: `Tap at (${x}, ${y})`,
      x: x,
      y: y,
      duration_ms: 50,
      conditions: []
    };
    
    recordingMacro.nodes.push(node);
    recordingNodes.push(node);
    
    // Update action history
    updateActionHistory();
  });
}

// Finish recording
function finishRecording() {
  recordingMode = false;
  
  // Build connections (sequential)
  for (let i = 0; i < recordingMacro.nodes.length - 1; i++) {
    recordingMacro.connections.push({
      from: recordingMacro.nodes[i].id,
      to: recordingMacro.nodes[i + 1].id,
      label: 'default'
    });
  }
  
  // Save via API
  saveMacroViaAPI(recordingMacro);
  
  // Hide recording overlay
  document.getElementById('recording-panel').style.display = 'none';
}

function updateActionHistory() {
  const history = document.getElementById('recording-actions');
  history.innerHTML = recordingNodes.map((node, i) => `
    <div class="action-item">
      <span>${i + 1}. ${node.name}</span>
      <button onclick="removeAction(${i})">Remove</button>
      <button onclick="editAction(${i})">Edit</button>
    </div>
  `).join('');
}
```

---

## Node Graph Editor Example (Frontend - Konva.js)

```javascript
// Initialize node graph canvas
const stage = new Konva.Stage({
  container: 'node-graph-canvas',
  width: window.innerWidth,
  height: 400
});

const layer = new Konva.Layer();
stage.add(layer);

// Node palette
const nodePalette = [
  {type: 'tap', name: 'Tap', color: '#FF6B6B'},
  {type: 'key', name: 'Key', color: '#4ECDC4'},
  {type: 'wait', name: 'Wait', color: '#45B7D1'},
  {type: 'ocr', name: 'OCR', color: '#FFA07A'},
  {type: 'loop', name: 'Loop', color: '#98D8C8'},
  {type: 'condition', name: 'Condition', color: '#F7DC6F'}
];

// Drag node from palette to canvas
function setupPaletteDrag() {
  nodePalette.forEach(item => {
    const btn = document.createElement('button');
    btn.textContent = item.name;
    btn.style.backgroundColor = item.color;
    btn.draggable = true;
    
    btn.addEventListener('dragstart', (e) => {
      e.dataTransfer.effectAllowed = 'copy';
      e.dataTransfer.setData('nodeType', item.type);
    });
    
    document.getElementById('node-palette').appendChild(btn);
  });
}

// Drop node onto canvas
function setupCanvasDrop() {
  const canvas = document.getElementById('node-graph-canvas');
  
  canvas.addEventListener('dragover', (e) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'copy';
  });
  
  canvas.addEventListener('drop', (e) => {
    e.preventDefault();
    
    const nodeType = e.dataTransfer.getData('nodeType');
    const x = e.offsetX;
    const y = e.offsetY;
    
    addNodeToGraph(nodeType, x, y);
  });
}

// Add node to graph
function addNodeToGraph(type, x, y) {
  const nodeId = `node_${Date.now()}`;
  
  const nodeGroup = new Konva.Group({
    x: x,
    y: y,
    draggable: true
  });
  
  const box = new Konva.Rect({
    width: 100,
    height: 60,
    fill: '#FF6B6B',
    stroke: '#333',
    strokeWidth: 2,
    cornerRadius: 5
  });
  
  const text = new Konva.Text({
    text: type,
    fontSize: 14,
    fontFamily: 'Calibri',
    fill: 'white',
    align: 'center',
    width: 100,
    padding: 10
  });
  
  // Output port (for connections)
  const outputPort = new Konva.Circle({
    x: 100,
    y: 30,
    radius: 5,
    fill: '#333'
  });
  
  nodeGroup.add(box, text, outputPort);
  nodeGroup.id = nodeId;
  nodeGroup.nodeType = type;
  
  layer.add(nodeGroup);
  layer.draw();
}
```

---

## Testing Macro Execution

```python
def test_macro_execution():
    """Test that macro executes correctly"""
    # Create simple macro
    macro = Macro(None, "Test", "")
    
    tap = MacroNode("n1", "tap", "Tap", x=640, y=720)
    wait = MacroNode("n2", "wait", "Wait", wait_type="time", time_ms=100)
    
    macro.add_node(tap)
    macro.add_node(wait)
    macro.add_connection(Connection("n1", "n2"))
    
    # Execute
    executor = MacroExecutor(macro, "192.168.1.152:5555")
    thread = executor.start()
    thread.join(timeout=5)
    
    # Verify
    assert executor.state == "stopped"
    assert len(executor.execution_log) == 2
    assert executor.execution_log[0]['message'].startswith("Executed tap")
    assert executor.execution_log[1]['message'].startswith("Executed wait")
    
    print("✓ Macro execution test passed")
```

---

## That's It!

Copy these examples and adapt them to your needs. All the building blocks are here!
