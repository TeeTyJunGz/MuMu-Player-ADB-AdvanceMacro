# MuMu ADB Macro System Specification

This document defines the complete macro system architecture for the MuMu Android Emulator Web GUI. Use this to implement, extend, or replicate the macro system across different AI agents and development environments.

---

## Overview

The macro system enables users to:
1. **Record** sequences of actions (taps, key inputs, waits)
2. **Visually edit** macros using a node-based workflow editor (like DaVinci Resolve)
3. **Add conditions** (color checks, pixel waits, OCR text matching)
4. **Execute** macros with full playback control
5. **Loop/repeat** actions with customizable iteration counts

---

## Data Model

### Macro Structure

```json
{
  "id": "macro_unique_id_timestamp",
  "name": "Macro Name",
  "description": "What this macro does",
  "created_at": "2026-07-04T03:46:00Z",
  "modified_at": "2026-07-04T03:46:00Z",
  "nodes": [
    { "id": "node_0", "type": "tap", ...},
    { "id": "node_1", "type": "wait", ...},
    { "id": "node_2", "type": "loop", ...}
  ],
  "connections": [
    { "from": "node_0", "to": "node_1" },
    { "from": "node_1", "to": "node_2" }
  ]
}
```

### Node Types

#### 1. **Tap Node** (Smart Tap)
```json
{
  "id": "node_N",
  "type": "tap",
  "name": "Tap Login Button",
  "x": 640,
  "y": 720,
  "duration_ms": 50,
  "conditions": [
    {
      "type": "color_check",
      "x": 640,
      "y": 720,
      "hex_color": "#FF5733",
      "tolerance_percent": 15,
      "operator": "equal"
    },
    {
      "type": "time_check",
      "operator": "after",
      "time": "10:30 AM"
    }
  ],
  "execute_if_all_conditions_met": true
}
```

**Fields:**
- `x`, `y`: Screen coordinates
- `duration_ms`: How long to hold the tap (default 50ms)
- `conditions`: Array of conditions that must be met before executing
- `execute_if_all_conditions_met`: Boolean (true=AND logic, false=OR logic)

---

#### 2. **Key Input Node** (Keyboard)
```json
{
  "id": "node_N",
  "type": "key",
  "name": "Type Password",
  "keys": ["enter", "a", "b", "c"],
  "delay_between_keys_ms": 50,
  "hold_keys": ["shift"],
  "text_input": "optional_text_string"
}
```

**Supported Keys:**
```
enter, escape, backspace, delete, tab, space
a-z, 0-9
up, down, left, right
home, end, pageup, pagedown
shift, ctrl, alt, meta (can be held for modifier)
f1-f12
```

---

#### 3. **Wait Node**
```json
{
  "id": "node_N",
  "type": "wait",
  "name": "Wait for Dialog",
  "wait_type": "time_or_pixel",
  "time_ms": 3000,
  "pixel_condition": {
    "x": 640,
    "y": 720,
    "hex_color": "#00FF00",
    "tolerance_percent": 10
  },
  "max_wait_ms": 10000,
  "fail_on_timeout": false
}
```

**wait_type options:**
- `"time"`: Wait for fixed duration (ms)
- `"pixel"`: Wait until pixel at (x,y) becomes specific color
- `"time_or_pixel"`: Wait for whichever comes first
- `"any_pixel_change"`: Wait until pixel at (x,y) changes from current color

---

#### 4. **OCR Node** (Text Recognition)
```json
{
  "id": "node_N",
  "type": "ocr",
  "name": "Read Login Error",
  "region": {
    "x1": 100,
    "y1": 300,
    "x2": 700,
    "y2": 400
  },
  "expected_text": "Invalid password",
  "match_type": "contains",
  "language": "eng",
  "store_result": "ocr_result_1",
  "conditional_branch": {
    "on_match": "node_5",
    "on_no_match": "node_6"
  }
}
```

**match_type options:**
- `"exact"`: Exact string match
- `"contains"`: Substring match
- `"regex"`: Regex pattern match
- `"not_contains"`: Inverted contains

**conditional_branch:**
- Routes execution to different next nodes based on OCR result
- Allows workflow branching logic

---

#### 5. **Loop Node**
```json
{
  "id": "node_N",
  "type": "loop",
  "name": "Repeat 5 Times",
  "loop_type": "fixed_count",
  "iterations": 5,
  "body_nodes": ["node_1", "node_2", "node_3"],
  "delay_between_iterations_ms": 500,
  "break_condition": {
    "type": "pixel_color",
    "x": 640,
    "y": 720,
    "hex_color": "#FF0000"
  }
}
```

**loop_type options:**
- `"fixed_count"`: Repeat N times
- `"while_true"`: Repeat until break_condition met
- `"until_color"`: Repeat until pixel becomes specific color

---

#### 6. **Condition Node** (Branching)
```json
{
  "id": "node_N",
  "type": "condition",
  "name": "Check if Connected",
  "condition": {
    "type": "pixel_color",
    "x": 640,
    "y": 50,
    "hex_color": "#00FF00",
    "tolerance_percent": 5
  },
  "true_branch": "node_5",
  "false_branch": "node_10"
}
```

---

#### 7. **Screenshot Node** (Debug)
```json
{
  "id": "node_N",
  "type": "screenshot",
  "name": "Capture Screen",
  "save_filename": "debug_screenshot_{{timestamp}}.png",
  "include_in_log": true
}
```

---

#### 8. **Delay/Pause Node**
```json
{
  "id": "node_N",
  "type": "delay",
  "name": "Pause 2 seconds",
  "delay_ms": 2000
}
```

---

## Node Connection Model

Nodes connect in a directed graph:

```json
{
  "connections": [
    {
      "from": "node_0",
      "to": "node_1",
      "label": "success"
    },
    {
      "from": "node_1",
      "to": "node_2",
      "label": "default"
    }
  ]
}
```

**Connection labels** (used for branching nodes):
- `"success"`, `"failure"`, `"true"`, `"false"`, `"default"`

---

## Macro Execution Model

### Playback State Machine

```
[IDLE] → [RECORDING] → [PAUSED] → [RUNNING] → [PAUSED/STOPPED]
  ↑                                              ↓
  ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ← ←
```

### Execution Flow

1. **Parse macro** into execution plan (topological sort of nodes)
2. **For each node:**
   - Evaluate conditions (if any)
   - If conditions pass OR no conditions, execute node action
   - Check for branches (condition/OCR nodes)
   - Move to next connected node
3. **On loop:**
   - Increment counter, check break condition
   - Jump back to loop start or exit
4. **On completion:**
   - Record execution log with timestamps and results
   - Return final state (success/failure/paused)

---

## Backend API Endpoints

### Macro Management

```
POST   /api/macros                    # Create new macro
GET    /api/macros                    # List all macros
GET    /api/macros/<id>               # Get single macro details
PUT    /api/macros/<id>               # Update macro
DELETE /api/macros/<id>               # Delete macro
```

### Macro Recording

```
POST   /api/macros/record/start       # Start recording mode (tap to capture coords)
POST   /api/macros/record/stop        # Stop recording
POST   /api/macros/record/add-action  # Add single action to recording
```

### Macro Execution

```
POST   /api/macros/<id>/play          # Start playback
POST   /api/macros/<id>/pause         # Pause playback
POST   /api/macros/<id>/resume        # Resume paused playback
POST   /api/macros/<id>/stop          # Stop playback
GET    /api/macros/<id>/status        # Get current playback status
GET    /api/macros/<id>/log           # Get execution log
```

### Utility Endpoints

```
POST   /api/color-picker              # Get pixel color at (x,y)
POST   /api/ocr/preview               # Preview OCR on region before adding to macro
POST   /api/screen-snapshot           # Capture current screen for visual reference
```

---

## Recording Mode UI/UX

### User Flow

1. **Click "Record New Macro"** → Opens recording mode UI
2. **Macro recording panel appears** with:
   - Live screen preview
   - "Tap to record" overlay indicator
   - Action history panel (shows recorded actions so far)
   - Quick action buttons: Add Delay, Add Wait, Add Key Input, etc.
3. **User taps on screen** → Automatically captures:
   - x, y coordinates
   - Optional: pixel color at tap location (for condition reference)
4. **For each tap:**
   - Show captured coordinates in action history
   - Allow editing (name, add conditions, adjust coordinates)
   - Option to insert waits/delays between actions
5. **Repeat until macro complete**
6. **Click "Finish Recording"** → Save macro and open editor

---

## Visual Workflow Editor (Node Graph UI)

### Layout

Left sidebar:
- Macro name + description editor
- Node palette (drag-to-add):
  - Tap, Key, Wait, OCR, Loop, Condition, Screenshot, Delay

Center canvas:
- Node-based visual workflow (like DaVinci Resolve)
- Nodes = boxes with inputs/outputs
- Connections = lines connecting nodes
- Drag node outputs to next node input to connect
- Right-click node → edit properties in side panel

Right sidebar:
- Node properties editor (changes based on selected node)
- Execution preview (shows what will happen)

Bottom:
- Playback controls (Play, Pause, Stop)
- Execution speed slider
- Log viewer (shows past executions)

### Node Visual Design

```
┌─────────────────────┐
│  [Tap Button]      │
├─────────────────────┤
│ x: 640, y: 720     │
│ Conditions: 1      │
├─────────────────────┤
│ ●──────────────────>│  (output port)
└─────────────────────┘

(input port on left, output port on right)
```

---

## Recording File Format (.macro.json)

```json
{
  "version": "1.0",
  "id": "macro_1720058788123",
  "name": "Login Flow",
  "description": "Logs into app and checks inbox",
  "created_at": "2026-07-04T03:46:28Z",
  "modified_at": "2026-07-04T03:50:00Z",
  "device_info": {
    "resolution": "1280x720",
    "android_version": "11"
  },
  "nodes": [
    {
      "id": "node_0",
      "type": "tap",
      "name": "Tap Email Field",
      "x": 200,
      "y": 300,
      "duration_ms": 50,
      "conditions": []
    },
    {
      "id": "node_1",
      "type": "key",
      "name": "Type Email",
      "text_input": "user@example.com",
      "delay_between_keys_ms": 50
    },
    {
      "id": "node_2",
      "type": "tap",
      "name": "Tap Next",
      "x": 640,
      "y": 500
    },
    {
      "id": "node_3",
      "type": "wait",
      "name": "Wait for Password Screen",
      "wait_type": "time",
      "time_ms": 1000
    },
    {
      "id": "node_4",
      "type": "tap",
      "name": "Tap Password Field",
      "x": 200,
      "y": 350
    },
    {
      "id": "node_5",
      "type": "key",
      "name": "Type Password",
      "text_input": "password123",
      "delay_between_keys_ms": 50
    },
    {
      "id": "node_6",
      "type": "tap",
      "name": "Tap Login",
      "x": 640,
      "y": 500,
      "conditions": [
        {
          "type": "color_check",
          "x": 640,
          "y": 500,
          "hex_color": "#2196F3",
          "tolerance_percent": 10,
          "operator": "equal"
        }
      ]
    },
    {
      "id": "node_7",
      "type": "wait",
      "name": "Wait for Login Success",
      "wait_type": "pixel",
      "pixel_condition": {
        "x": 100,
        "y": 100,
        "hex_color": "#4CAF50"
      },
      "max_wait_ms": 5000
    }
  ],
  "connections": [
    { "from": "node_0", "to": "node_1" },
    { "from": "node_1", "to": "node_2" },
    { "from": "node_2", "to": "node_3" },
    { "from": "node_3", "to": "node_4" },
    { "from": "node_4", "to": "node_5" },
    { "from": "node_5", "to": "node_6" },
    { "from": "node_6", "to": "node_7" }
  ]
}
```

---

## Implementation Checklist

### Phase 1: Core Backend (Priority 1)
- [ ] Create macro data models (`Macro`, `Node`, `Connection` classes)
- [ ] Implement macro storage (JSON file or DB)
- [ ] Build node executor engine (execute single node)
- [ ] Build macro executor (execute full workflow)
- [ ] Implement playback state machine
- [ ] Create macro API endpoints
- [ ] Add pixel color picker utility
- [ ] Add OCR preview endpoint (optional: use Tesseract/EasyOCR)

### Phase 2: Recording Mode (Priority 2)
- [ ] Recording state management
- [ ] Auto-capture coordinates on screen tap
- [ ] Action history display
- [ ] Quick-add buttons (delay, wait, etc.)
- [ ] Save recording as macro

### Phase 3: Visual Editor (Priority 3)
- [ ] Node graph canvas (use D3.js or jsPlumb)
- [ ] Drag-to-add nodes from palette
- [ ] Connect nodes by dragging outputs to inputs
- [ ] Node properties editor panel
- [ ] Edit node connections (delete, redirect)
- [ ] Save/load visual layouts

### Phase 4: Advanced Features (Priority 4)
- [ ] OCR node with text preview
- [ ] Condition nodes with branching
- [ ] Loop nodes with break conditions
- [ ] Macro execution history/logs
- [ ] Playback speed control
- [ ] Variable system (store OCR results, reuse in conditions)

---

## Technology Stack Recommendations

**Backend:**
- Python Flask (existing)
- For OCR: Tesseract or EasyOCR
- Storage: JSON files or SQLite

**Frontend:**
- Canvas library: Konva.js or Fabric.js (for node graph)
- Or use a dedicated node-editor library: Rete.js, Node-RED visual editor
- State management: Vue.js with store or plain vanilla JS

**Data:**
- Macro files stored as `.macro.json` in `/macros/` directory
- Execution logs stored as `.log.json`

---

## Example Workflow: Mobile Game Login Macro

```
[START] 
  ↓
[Tap Email Field] (x: 200, y: 300)
  ↓
[Type: user@email.com] (key input)
  ↓
[Wait 500ms]
  ↓
[Tap Password Field] (x: 200, y: 350)
  ↓
[Type: mypass123] (key input)
  ↓
[Tap Login Button] (x: 640, y: 500)
  ├─ Condition: Button is blue (#2196F3)
  ↓
[Wait for success icon] (pixel: #4CAF50)
  ├─ Max wait: 5000ms
  ├─ On timeout: Loop and retry (max 3x)
  ↓
[Screenshot] (for verification)
  ↓
[END - Success]
```

---

## Testing Scenarios

1. **Simple tap sequence** - Tap 3 buttons in order
2. **With conditions** - Tap only if button is green
3. **With delays** - Tap, wait 2s, tap next
4. **With OCR** - Read text and branch based on content
5. **With loop** - Repeat tap 5 times
6. **With error handling** - Retry on failure

---

## Notes for Other AIs

When implementing this spec:

1. **Always preserve node IDs and connections** - they define workflow structure
2. **Validate node types** - only accept known types from this spec
3. **Condition evaluation should use AND logic by default** - unless `execute_if_all_conditions_met` is false
4. **OCR should be optional** - gracefully degrade if not available
5. **Recording mode requires real-time screen overlay** - show tap points as they occur
6. **File format is JSON** - version 1.0, ensure compatibility for future versions
7. **Execution logs must include timestamps** - for debugging and analysis

---

## Future Enhancements

- [ ] Variable storage and reuse (${var_name})
- [ ] Screenshot comparisons (image matching)
- [ ] Multi-device macro execution
- [ ] Macro library/sharing
- [ ] Conditional branches with complex logic
- [ ] Async actions (parallel node execution)
- [ ] Macro debugging mode with breakpoints
- [ ] Performance profiling (node timing)
- [ ] Macro versioning and rollback
