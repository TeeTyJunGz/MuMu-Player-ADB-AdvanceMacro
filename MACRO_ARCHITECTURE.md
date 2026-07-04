# Macro System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         WEB GUI (Browser - Frontend)                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                               │
│  ┌──────────────────────┐  ┌──────────────────────┐  ┌──────────────────┐  │
│  │  Macro List Panel    │  │  Recording Mode UI   │  │  Visual Editor   │  │
│  │                      │  │                      │  │  (Node Graph)    │  │
│  │ • List all macros    │  │ • Live screen view   │  │                  │  │
│  │ • Create/Delete      │  │ • Tap overlay        │  │ • Drag nodes     │  │
│  │ • Open in editor     │  │ • Action history     │  │ • Connect nodes  │  │
│  └──────────────────────┘  └──────────────────────┘  └──────────────────┘  │
│           │                         │                         │              │
│           │ GET /api/macros         │ POST /record/add-action │ PUT /macros  │
│           │ POST /api/macros        │                         │              │
│           │ DELETE /api/macros/{id} │                         │              │
│           └─────────────────────────┴─────────────────────────┘              │
│                                     │                                        │
└─────────────────────────────────────┼────────────────────────────────────────┘
                                      │ HTTP/JSON
                ┌─────────────────────┴──────────────────┐
                │                                        │
┌───────────────┴──────────────────┐  ┌────────────────┴─────────────────┐
│                                  │  │                                  │
│    FLASK BACKEND (Python)        │  │   ADB / Android Device           │
│                                  │  │                                  │
│ ┌──────────────────────────────┐ │  │ ┌────────────────────────────┐  │
│ │  Macro API Endpoints         │ │  │ │  Device: MuMu Emulator     │  │
│ │                              │ │  │ │  Serial: 192.168.1.152:555 │  │
│ │ GET  /api/macros             │ │  │ │                            │  │
│ │ POST /api/macros             │ │  │ │ • Tap coordinates          │  │
│ │ GET  /api/macros/{id}        │ │  │ │ • Key input                │  │
│ │ PUT  /api/macros/{id}        │ │  │ │ • Capture screen           │  │
│ │ DELETE /api/macros/{id}      │ │  │ │ • Get pixel color          │  │
│ │                              │ │  │ └────────────────────────────┘  │
│ │ POST /api/macros/{id}/play   │ │  │                                  │
│ │ POST /api/macros/{id}/pause  │ │  │ ┌────────────────────────────┐  │
│ │ POST /api/macros/{id}/stop   │ │  │ │  ADB Commands              │  │
│ │ GET  /api/macros/{id}/status │ │  │ │                            │  │
│ │                              │ │  │ │ • input tap x y            │  │
│ │ POST /api/color-picker       │ │  │ │ • input text "text"        │  │
│ │ POST /api/ocr/preview        │ │  │ │ • input keyevent CODE      │  │
│ └──────────────────────────────┘ │  │ │ • screencap /tmp/pic.png   │  │
│           │                       │  │ └────────────────────────────┘  │
│           │                       │  │                                  │
│ ┌─────────┴─────────────────────┐ │  └──────────────────────────────────┘
│ │  Macro Core (models.py)       │ │
│ │                               │ │
│ │ • Macro (container)           │ │
│ │ • MacroNode (tap/key/wait...) │ │
│ │ • Connection (tap A→B→C)      │ │
│ │ • Condition (color/time)      │ │
│ └───────────┬───────────────────┘ │
│             │                     │
│ ┌───────────┴─────────────────────┐ │
│ │  Storage Layer (storage.py)     │ │
│ │                                 │ │
│ │ • Save macro to JSON            │ │
│ │ • Load macro from JSON          │ │
│ │ • List all macros              │ │
│ │ • Delete macro file            │ │
│ └───────────┬─────────────────────┘ │
│             │                       │
│             ▼                       │
│  ┌──────────────────────────────┐  │
│  │  macros_data/                │  │
│  │  ├── macro_1720058788123.    │  │
│  │  │   macro.json             │  │
│  │  └── macro_1720058800456.   │  │
│  │      macro.json             │  │
│  └──────────────────────────────┘  │
│                                     │
│ ┌──────────────────────────────────┐│
│ │  Executor (executor.py)          ││
│ │                                  ││
│ │ Current Macro: macro_123         ││
│ │ State: running/paused/stopped    ││
│ │                                  ││
│ │ ┌────────────────────────────┐   ││
│ │ │ Main Execution Loop:       │   ││
│ │ │                            │   ││
│ │ │ 1. Find start node         │   ││
│ │ │ 2. Execute node:           │   ││
│ │ │    • Check conditions      │   ││
│ │ │    • Perform action        │   ││
│ │ │    • Record log entry      │   ││
│ │ │ 3. Follow connection       │   ││
│ │ │ 4. Repeat until end        │   ││
│ │ │ 5. Return status + log     │   ││
│ │ └────────────────────────────┘   ││
│ │                                  ││
│ │ ┌─ Threading Model ─────────┐   ││
│ │ │  Background Thread:        │   ││
│ │ │  • Run macro executor      │   ││
│ │ │  • Update log in real-time │   ││
│ │ │  • Main thread stays free  │   ││
│ │ │  • UI polls /status        │   ││
│ │ └────────────────────────────┘   ││
│ └──────────────────────────────────┘│
│                                     │
└─────────────────────────────────────┘
```

---

## Data Flow Diagram

```
User Creates Macro
        │
        ▼
┌──────────────────────────────────────────┐
│ Visual Editor UI (node graph canvas)     │
│ • Drag nodes onto canvas                 │
│ • Set node properties (x, y, conditions) │
│ • Connect nodes with arrows              │
└──────────────────────────────────────────┘
        │
        │ User clicks "Save"
        ▼
┌──────────────────────────────────────────┐
│ macros/models.py                         │
│ • Convert UI nodes to MacroNode objects  │
│ • Build Macro with connections          │
│ • Serialize to dict                      │
└──────────────────────────────────────────┘
        │
        │ Call MacroStorage.save(macro)
        ▼
┌──────────────────────────────────────────┐
│ macros/storage.py                        │
│ • Convert Macro dict to JSON             │
│ • Write to macros_data/macro_xxxxx.json  │
│ • File saved on disk                     │
└──────────────────────────────────────────┘
        
───────────────────────────────────────────────

User Plays Macro
        │
        ▼
┌──────────────────────────────────────────┐
│ POST /api/macros/{id}/play               │
│ • Load macro from storage                │
│ • Create MacroExecutor instance          │
│ • Start executor in background thread    │
└──────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────┐
│ macros/executor.py (Background Thread)   │
│                                          │
│ 1. Find start node                       │
│ 2. For each node:                        │
│    • Get MacroNode from macro.nodes[id]  │
│    • Call _execute_node(node)            │
│    • Determine next node_id              │
│    • Follow connections                  │
│ 3. Record to execution_log               │
│ 4. Handle branching (conditions, loops)  │
│ 5. Return final state                    │
└──────────────────────────────────────────┘
        │
        ├─ For each node type:
        │
        ├─ TAP:     adb shell input tap x y
        │
        ├─ KEY:     adb shell input text "..."
        │           adb shell input keyevent CODE
        │
        ├─ WAIT:    sleep(ms) OR loop until pixel_color match
        │
        ├─ OCR:     tesseract on region → compare text
        │
        ├─ SCREENSHOT: screencap /tmp/pic.png
        │
        └─ LOOP:    execute body_nodes[] N times
        │
        ▼
┌──────────────────────────────────────────┐
│ UI polls GET /api/macros/{id}/status     │
│ • Gets current state                     │
│ • Gets execution log (last 50 entries)   │
│ • Updates log view in real-time          │
└──────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────┐
│ Macro Execution Complete                 │
│ • Status: success/failure/paused         │
│ • Log: all timestamped events            │
│ • User can save log for debugging        │
└──────────────────────────────────────────┘
```

---

## Recording Mode Flow

```
User Clicks "Record Macro"
        │
        ▼
┌──────────────────────────────────────────┐
│ Start Recording Mode                     │
│ • Create empty Macro object              │
│ • Show recording panel overlay           │
│ • Enable tap detection on screen preview │
│ • Set mode = "recording"                 │
└──────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────┐
│ User taps screen at point (640, 720)     │
│ • JavaScript captures tap coordinates    │
│ • POST /record/add-action                │
│ • Tap: x=640, y=720 added to macro       │
│ • Display in action history panel        │
└──────────────────────────────────────────┘
        │
        ├─ User can:
        │  • Edit tap (add conditions)
        │  • Click "Add Delay" → Insert wait node
        │  • Click "Add Key" → Insert key node
        │  • Continue tapping...
        │
        ▼
┌──────────────────────────────────────────┐
│ User Clicks "Finish Recording"           │
│ • Stop recording mode                    │
│ • Open macro in visual editor            │
│ • Show nodes and connections             │
│ • Ready to save or play                  │
└──────────────────────────────────────────┘
        │
        ▼
┌──────────────────────────────────────────┐
│ User Saves Macro                         │
│ • Call MacroStorage.save(macro)          │
│ • JSON file written to disk              │
│ • Macro now in /api/macros list          │
└──────────────────────────────────────────┘
```

---

## Execution State Machine

```
                ┌─────────────────┐
                │      IDLE       │
                │  (no macro)     │
                └────────┬────────┘
                         │
                    User clicks Play
                         │
                         ▼
                ┌─────────────────┐
                │    RUNNING      │
                │  (executing)    │
                └────┬───────┬────┘
                     │       │
           Pause button  Stop button / Error
                     │       │
                     ▼       ▼
            ┌──────────────┐ ┌───────────────┐
            │   PAUSED     │ │    STOPPED    │
            │ (can resume) │ │ (back to IDLE)│
            └──────┬───────┘ └───────────────┘
                   │
              Resume button
                   │
                   ▼
            ┌──────────────┐
            │    RUNNING   │
            │ (continued)  │
            └──────┬───────┘
                   │
              Execution complete
                   │
                   ▼
            ┌──────────────┐
            │ STOPPED      │
            │ (completed)  │
            └──────┬───────┘
                   │
              Execution log saved
                   │
                   ▼
            ┌─────────────────┐
            │      IDLE       │
            │  (macro done)   │
            └─────────────────┘
```

---

## Node Connection Resolution (Finding Next Node)

```
Current Node: tap_button (node_0)

Step 1: Is this node a branching node?
        (condition, ocr, loop)
        │
        ├─ YES: Return branch target
        │       ├─ condition: return true_branch or false_branch
        │       ├─ ocr: return on_match or on_no_match
        │       └─ loop: after iterations, return next node
        │
        └─ NO: Continue to step 2

Step 2: Get all connections where from_id == node_0
        macro.connections = [
          { from: node_0, to: node_1, label: "default" },
          { from: node_0, to: node_2, label: "error" },
        ]
        
        Filter for label == "default"
        Result: node_1

Step 3: Move to node_1 (step 2)
```

---

## Storage Format Example

```
File: macros_data/macro_1720058788123.macro.json

{
  "id": "macro_1720058788123",
  "name": "Login to App",
  "description": "Logs in with email and password",
  "created_at": "2026-07-04T03:46:28Z",
  "modified_at": "2026-07-04T03:50:00Z",
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
    }
  ],
  "connections": [
    {
      "from": "node_0",
      "to": "node_1",
      "label": "default"
    }
  ]
}
```
