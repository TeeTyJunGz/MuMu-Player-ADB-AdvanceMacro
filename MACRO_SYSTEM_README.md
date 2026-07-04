# MuMu ADB Macro System - Complete Implementation Package

This package contains everything needed to implement a professional macro recording and playback system for the MuMu Android Emulator web GUI.

---

## 📚 Documentation Files

### For Understanding the System
1. **MACRO_SYSTEM_SPECIFICATION.md** - Complete technical specification
   - Node types and data models
   - API endpoints
   - File format and schema
   - Implementation checklist

2. **MACRO_ARCHITECTURE.md** - System design and diagrams
   - Component architecture
   - Data flow diagrams
   - State machines
   - Execution logic

3. **MACRO_QUICK_REFERENCE.md** - Quick lookup guide
   - Node types summary table
   - API endpoints list
   - Testing with curl
   - Troubleshooting tips

### For Implementation
4. **MACRO_IMPLEMENTATION_GUIDE.md** - Step-by-step implementation guide
   - Phase 1: Backend (models, storage, executor)
   - Phase 2: Recording mode UI
   - Phase 3: Visual editor UI
   - Testing checklist
   - Common pitfalls to avoid

---

## 🎯 What This System Does

### Core Features
- ✅ **Smart Tap** - Click screen coordinates with optional conditions
- ✅ **Keyboard Input** - Type text and press keys
- ✅ **Wait Actions** - Pause for fixed time or until pixel color changes
- ✅ **OCR Text Recognition** - Read screen text and make decisions based on content
- ✅ **Looping** - Repeat actions N times or until condition met
- ✅ **Conditional Branching** - Execute different paths based on conditions
- ✅ **Visual Workflow Editor** - Node-based (like DaVinci Resolve)
- ✅ **Recording Mode** - Tap screen to auto-record coordinates
- ✅ **Full Playback Control** - Play, pause, resume, stop with real-time logs

### Example Use Cases
- **Mobile Game Bot** - Auto-login, farm resources, navigate menus
- **App Testing** - Automate test sequences with visual validation
- **Data Entry** - Fill forms, capture results, save to file
- **Content Creation** - Record action sequences for documentation

---

## 🗂️ Project Structure After Implementation

```
MuMuADB/
├── app.py                              # Updated: add macro routes
├── requirements.txt                    # Updated: add pytesseract
│
├── macros/                             # NEW FOLDER
│   ├── __init__.py                     # Empty file
│   ├── models.py                       # Macro/Node/Connection classes
│   ├── storage.py                      # JSON file save/load
│   ├── executor.py                     # Execute macros (core logic)
│   └── ocr.py                          # Optional: OCR utilities
│
├── macros_data/                        # NEW FOLDER: Saved macros
│   ├── macro_1720058788123.macro.json
│   ├── macro_1720058800456.macro.json
│   └── ...
│
├── templates/
│   ├── index.html                      # Updated: add macro UI
│   ├── macro_panel.html                # NEW: Macro editor
│   └── macro_recorder.html             # NEW: Recording UI
│
├── MACRO_SYSTEM_SPECIFICATION.md       # System spec
├── MACRO_ARCHITECTURE.md               # Design diagrams
├── MACRO_IMPLEMENTATION_GUIDE.md       # Step-by-step guide
└── MACRO_QUICK_REFERENCE.md            # Quick lookup
```

---

## 🚀 Quick Start (5 Minutes)

### 1. Read Core Specification
Open: `MACRO_SYSTEM_SPECIFICATION.md`
- Understand node types (tap, key, wait, ocr, loop, condition)
- Review data model structure
- See example macro JSON

### 2. Review Architecture
Open: `MACRO_ARCHITECTURE.md`
- See component relationships
- Understand execution flow
- Study state machine

### 3. Follow Implementation Guide
Open: `MACRO_IMPLEMENTATION_GUIDE.md`
- Phase 1: Create `macros/models.py`, `macros/storage.py`, `macros/executor.py`
- Phase 2: Add Flask API endpoints
- Phase 3: Build frontend UI (optional but recommended)

### 4. Use Quick Reference
Open: `MACRO_QUICK_REFERENCE.md`
- Lookup API endpoints
- Test with curl examples
- Troubleshoot issues

---

## 💾 Installation Steps

### Step 1: Add Dependencies
```bash
pip install pytesseract pillow
```

### Step 2: Create Macro Folders
```bash
mkdir macros
mkdir macros_data
touch macros/__init__.py
```

### Step 3: Implement Backend (Copy from MACRO_IMPLEMENTATION_GUIDE.md)
- Create `macros/models.py`
- Create `macros/storage.py`
- Create `macros/executor.py`
- Add routes to `app.py`

### Step 4: Test Backend Endpoints
```bash
# Start Flask
python app.py

# In another terminal, test:
curl http://127.0.0.1:5000/api/macros
```

### Step 5: Add Frontend (Optional)
- Create `templates/macro_panel.html`
- Create `templates/macro_recorder.html`
- Update `templates/index.html`

---

## 🔧 File Descriptions

### Backend Files (Required)

**macros/models.py** (~150 lines)
- `Macro` class - Container for macro
- `MacroNode` class - Individual action/node
- `Connection` class - Links between nodes
- `Condition` class - Pre-execution condition

**macros/storage.py** (~60 lines)
- `MacroStorage.save(macro)` - Write to JSON file
- `MacroStorage.load(macro_id)` - Read from JSON file
- `MacroStorage.list_all()` - Get all macro IDs
- `MacroStorage.delete(macro_id)` - Remove macro

**macros/executor.py** (~300 lines, core logic)
- `MacroExecutor` class - Runs macros
- `_execute()` - Main execution loop
- `_execute_node()` - Execute single node
- Support for tap, key, wait, screenshot, etc.

### Frontend Files (Optional but Recommended)

**templates/macro_panel.html**
- Macro list/editor UI
- Node palette (drag nodes)
- Node graph canvas
- Properties panel

**templates/macro_recorder.html**
- Recording mode overlay
- Action history
- Quick action buttons

### Documentation Files (Reference)

Each document focuses on a specific aspect:
- **SPECIFICATION** - What to build
- **ARCHITECTURE** - How it works
- **QUICK_REFERENCE** - Quick lookup
- **IMPLEMENTATION_GUIDE** - How to build it

---

## 📋 Implementation Checklist

### Phase 1: Backend (Priority 1)
- [ ] Create `macros/models.py` with Macro, MacroNode, Connection classes
- [ ] Create `macros/storage.py` with save/load functions
- [ ] Create `macros/executor.py` with execution engine
- [ ] Add Flask API endpoints to `app.py`
- [ ] Test endpoints with curl
- [ ] Verify macro save/load works

### Phase 2: Recording Mode (Priority 2)
- [ ] Create recording mode toggle in UI
- [ ] Capture tap coordinates on screen click
- [ ] Display action history
- [ ] Save recording as macro
- [ ] Test recording and playback

### Phase 3: Visual Editor (Priority 3)
- [ ] Create node graph canvas (use Konva.js or similar)
- [ ] Drag-to-add nodes from palette
- [ ] Connect nodes with lines
- [ ] Edit node properties in right panel
- [ ] Save/load visual layouts
- [ ] Test creating complex workflows

### Phase 4: Advanced Features (Priority 4)
- [ ] Add OCR support (if tesseract available)
- [ ] Implement condition branching
- [ ] Support loop nodes
- [ ] Add execution history/logs
- [ ] Playback speed control

---

## 🧪 Testing Strategy

### Unit Tests
```python
# Test models
macro = Macro("id", "Test")
node = MacroNode("n1", "tap", "Tap Button", x=640, y=720)
macro.add_node(node)
assert len(macro.nodes) == 1

# Test storage
MacroStorage.save(macro)
loaded = MacroStorage.load(macro.id)
assert loaded.name == "Test"
```

### API Tests
```bash
# Create macro
curl -X POST http://127.0.0.1:5000/api/macros \
  -H "Content-Type: application/json" \
  -d '{"name":"Test","description":"Test macro"}'

# Play macro
curl -X POST http://127.0.0.1:5000/api/macros/macro_123/play \
  -H "Content-Type: application/json" \
  -d '{"serial":"192.168.1.152:5555"}'

# Check status
curl http://127.0.0.1:5000/api/macros/macro_123/status
```

### Integration Tests
1. Create macro programmatically
2. Save to disk
3. Load from disk
4. Execute macro
5. Verify execution log
6. Check device state changed correctly

---

## 🎓 Learning Resources

### Node Types to Understand First
1. **Tap** - Simple click, easiest to implement
2. **Wait** - Essential for synchronization
3. **Key** - Text input support
4. **Loop** - Repetition logic
5. **Condition** - Branching
6. **OCR** - Advanced text recognition

### Concepts to Master
1. **Workflow graphs** - Nodes connected by edges
2. **Topological sorting** - Execute in correct order
3. **State machines** - Running/paused/stopped
4. **Thread safety** - Background execution
5. **Serialization** - Save/load from JSON

---

## ⚙️ Configuration

### Executor Settings (in executor.py)
```python
MAX_WAIT_TIMEOUT = 10000  # ms
DEFAULT_TAP_DURATION = 50  # ms
DEFAULT_KEY_DELAY = 50    # ms
EXECUTION_LOG_MAX_SIZE = 1000  # entries
```

### Storage Settings (in storage.py)
```python
MACROS_DIR = "macros_data"
FILE_FORMAT = ".macro.json"
AUTO_BACKUP = False
```

---

## 🐛 Troubleshooting

### Macro doesn't execute
- Check if start node exists (no incoming connections)
- Verify all node IDs in connections exist
- Check execution log for error messages

### Conditions not working
- Verify pixel color format: `#RRGGBB`
- Check tolerance percentage is reasonable (0-100)
- Test with `color-picker` endpoint first

### OCR not working
- Install tesseract: `pip install pytesseract`
- On Windows: `choco install tesseract`
- Set correct language code (default: "eng")
- Ensure region boundaries are valid

### Recording mode issues
- Verify screen coordinates are correct
- Check that device is connected
- Ensure permissions are set correctly

---

## 🔐 Security Considerations

1. **File permissions** - `macros_data/` should be readable/writable only by app
2. **Input validation** - Sanitize macro name and description
3. **Command injection** - Escape adb commands properly
4. **Rate limiting** - Optional: limit macro creation/execution
5. **Authentication** - Optional: add user authentication before macro access

---

## 📈 Performance Tips

1. Use fixed delays instead of polling when possible
2. Cache screen captures if needed multiple times
3. Batch operations (e.g., multiple taps) when possible
4. Use threading for long-running operations
5. Profile executor to find bottlenecks

---

## 🔮 Future Enhancements

- [ ] Variable system (${variable_name})
- [ ] Screenshot image matching
- [ ] Multi-device macro execution
- [ ] Macro library/marketplace
- [ ] Async parallel node execution
- [ ] Macro versioning
- [ ] Execution analytics dashboard
- [ ] AI-powered macro suggestions
- [ ] Mobile app for recording macros
- [ ] Cloud sync for macros

---

## 📞 Getting Help

1. Check **MACRO_QUICK_REFERENCE.md** for common issues
2. Review **MACRO_ARCHITECTURE.md** for design questions
3. Refer to **MACRO_IMPLEMENTATION_GUIDE.md** for step-by-step help
4. Read **MACRO_SYSTEM_SPECIFICATION.md** for detailed specs

---

## 📄 License

This macro system specification and implementation guide is provided as-is for use in the MuMu ADB project.

---

## 🎉 You're Ready!

Everything you need is in these documentation files. Start with the MACRO_IMPLEMENTATION_GUIDE.md and follow each phase step-by-step. You'll have a working macro system in a few hours!

**Happy automating! 🚀**
