# Macro System Quick Reference

## Node Types Summary

| Type | Purpose | Key Fields |
|------|---------|-----------|
| **tap** | Smart click on screen | `x`, `y`, `duration_ms`, `conditions[]` |
| **key** | Keyboard input | `text_input`, `keys[]`, `delay_between_keys_ms` |
| **wait** | Pause execution | `wait_type` (time/pixel), `time_ms`, `pixel_condition` |
| **ocr** | Read screen text | `region{}`, `expected_text`, `match_type` (exact/contains/regex) |
| **loop** | Repeat actions | `loop_type`, `iterations`, `body_nodes[]`, `break_condition` |
| **condition** | Branch logic | `condition{}`, `true_branch`, `false_branch` |
| **screenshot** | Debug capture | `save_filename` |
| **delay** | Simple pause | `delay_ms` |

---

## Condition Types

```json
{
  "color_check": {
    "x": 640,
    "y": 720,
    "hex_color": "#FF5733",
    "tolerance_percent": 15,
    "operator": "equal"
  },
  "time_check": {
    "operator": "after",
    "time": "10:30 AM"
  },
  "pixel_color": {
    "x": 100,
    "y": 100,
    "hex_color": "#00FF00",
    "tolerance_percent": 5
  }
}
```

---

## Workflow Execution Order

1. Find **start node** (no incoming connections)
2. **Execute current node**
   - Check conditions (AND/OR logic)
   - Perform action (tap, key, wait, etc.)
   - Return result
3. **Determine next node**
   - If branch node: follow branch
   - Else: follow default connection
4. **Move to next node** (step 2)
5. **Loop until** no more connections or stop signal

---

## File Locations

```
MuMuADB/
├── app.py                          # Main Flask app (add macro routes here)
├── requirements.txt                # Add: pytesseract>=0.3.10
├── macros/                         # NEW: Create this folder
│   ├── __init__.py                # Empty init file
│   ├── models.py                  # Macro/Node/Connection classes
│   ├── storage.py                 # Save/load macros from disk
│   ├── executor.py                # Execute macros
│   └── ocr.py                     # Optional OCR utilities
├── macros_data/                   # NEW: Folder for .macro.json files
│   └── macro_xxxxx.macro.json     # Individual macro files
└── templates/
    ├── index.html                 # Main UI
    └── macro_panel.html           # NEW: Macro editor panel
```

---

## Creating a Macro Programmatically

```python
from macros.models import Macro, MacroNode, Connection
from macros.storage import MacroStorage

# Create macro
macro = Macro(None, "My First Macro", "Logs into app")

# Add nodes
tap_node = MacroNode("n1", "tap", "Tap Login", x=640, y=500, duration_ms=50)
macro.add_node(tap_node)

wait_node = MacroNode("n2", "wait", "Wait 2s", wait_type="time", time_ms=2000)
macro.add_node(wait_node)

# Connect nodes
macro.add_connection(Connection("n1", "n2"))

# Save
MacroStorage.save(macro)
```

---

## API Endpoints

### Macro CRUD
```
GET    /api/macros                      # List all
POST   /api/macros                      # Create
GET    /api/macros/{id}                 # Get one
PUT    /api/macros/{id}                 # Update
DELETE /api/macros/{id}                 # Delete
```

### Playback
```
POST   /api/macros/{id}/play            # Start
POST   /api/macros/{id}/pause           # Pause
POST   /api/macros/{id}/resume          # Resume
POST   /api/macros/{id}/stop            # Stop
GET    /api/macros/{id}/status          # Get status + log
```

### Utilities
```
POST   /api/color-picker                # Get pixel color at (x,y)
POST   /api/ocr/preview                 # Preview OCR on region
POST   /api/screen-snapshot             # Capture current screen
```

---

## Testing Endpoints with curl

```bash
# List macros
curl http://127.0.0.1:5000/api/macros

# Create macro
curl -X POST http://127.0.0.1:5000/api/macros \
  -H "Content-Type: application/json" \
  -d '{"name":"Test Macro","description":"Test"}'

# Get pixel color at 640,720
curl -X POST http://127.0.0.1:5000/api/color-picker \
  -H "Content-Type: application/json" \
  -d '{"x":640,"y":720}'

# Play macro
curl -X POST http://127.0.0.1:5000/api/macros/macro_123/play \
  -H "Content-Type: application/json" \
  -d '{"serial":"192.168.1.152:5555"}'
```

---

## Recording Mode Workflow

1. Click "Start Recording"
2. Recording panel appears with tap overlay
3. Each time user taps screen:
   - Capture x, y coordinates
   - Get pixel color (optional)
   - Add to action history
4. User can:
   - Edit action details (add conditions)
   - Insert delays/waits
   - Remove actions
5. Click "Finish Recording"
6. Macro saved, opens in editor

---

## Visual Editor Workflow

1. Drag node from palette onto canvas
2. Set node properties in right panel
3. Drag output port of node to input port of next node
4. Connection line appears
5. Right-click node → Edit/Delete/Duplicate
6. Click Play button to execute
7. Watch execution log in real-time
8. Save macro automatically

---

## Execution Log Format

```json
[
  {
    "timestamp": "2026-07-04T03:46:28.123Z",
    "level": "info",
    "message": "Executed tap: Tap Login - Result: {\"success\": true}",
    "node_id": "node_0"
  },
  {
    "timestamp": "2026-07-04T03:46:30.456Z",
    "level": "info",
    "message": "Executed wait: Wait for Dialog - Result: {\"success\": true}",
    "node_id": "node_1"
  }
]
```

---

## Android Keycodes

Common keycodes for `adb shell input keyevent`:

```
ENTER        66
ESCAPE       111
BACKSPACE    67
TAB          61
SPACE        62
HOME         122
END          123
PAGE_UP      92
PAGE_DOWN    93
UP           19
DOWN         20
LEFT         21
RIGHT        22
F1-F12       131-142
```

---

## Pixel Color Format

Always use hex colors with `#` prefix:
- `#FF0000` - Red
- `#00FF00` - Green
- `#0000FF` - Blue
- `#FFFFFF` - White
- `#000000` - Black

RGB also supported but convert to hex first:
- RGB (255, 87, 51) → `#FF5733`

---

## Tolerance Percentage Explained

Tolerance allows fuzzy color matching:

```
Target: #FF5733 (RGB: 255, 87, 51)
Tolerance: 15%

Acceptable range:
  Red:   255 ± (255 × 0.15) = 216-255
  Green: 87 ± (255 × 0.15) = 48-126
  Blue:  51 ± (255 × 0.15) = 12-90
```

---

## Macro JSON Schema Validation

Required fields for macro:
- `id`: unique identifier (string)
- `name`: display name (string)
- `nodes`: array of node objects
- `connections`: array of connection objects

Required fields for node:
- `id`: unique within macro (string)
- `type`: node type (string, from NodeType enum)
- `name`: display name (string)

Optional fields depend on node type (see spec for details)

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| Macro doesn't execute | Check that start node has no incoming connections |
| Node skipped | Conditions not met - check condition evaluation |
| Infinite loop | Add break condition or use fixed iteration count |
| Coordinates wrong | Verify screen resolution matches recording resolution |
| Slow playback | Reduce delays, increase execution speed setting |
| OCR not working | Check tesseract installed, region boundaries correct |

---

## Performance Tips

1. **Use fixed delays** instead of polling
2. **Group similar taps** in loops when possible
3. **Use pixel wait** instead of fixed delay when checking for UI changes
4. **Minimize OCR usage** (it's CPU intensive)
5. **Test with playback speed** set to slow first

---

## Future Extensions

- [ ] Variable system (`${variable_name}`)
- [ ] Screenshot image matching
- [ ] Multi-device execution
- [ ] Macro library/templates
- [ ] Async parallel nodes
- [ ] Macro versioning
- [ ] Execution analytics
