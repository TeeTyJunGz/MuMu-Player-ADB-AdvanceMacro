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
    LOOP_START = "loop_start"
    LOOP_END = "loop_end"
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
