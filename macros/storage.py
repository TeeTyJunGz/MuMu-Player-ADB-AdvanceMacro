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
        """List all macro IDs, respecting saved order if it exists"""
        MacroStorage.ensure_dir()
        files = os.listdir(MACROS_DIR)
        all_ids = [f.replace(".macro.json", "") for f in files if f.endswith(".macro.json")]
        
        order_path = os.path.join(MACROS_DIR, "macro_order.json")
        if os.path.exists(order_path):
            try:
                with open(order_path, 'r') as f:
                    saved_order = json.load(f)
                # Keep saved ones that still exist
                ordered = [x for x in saved_order if x in all_ids]
                # Append any new ones that aren't in the order list yet
                new_ones = [x for x in all_ids if x not in ordered]
                return ordered + new_ones
            except Exception:
                pass
                
        return all_ids
        
    @staticmethod
    def save_order(macro_ids: List[str]):
        """Save the custom ordering of macros"""
        MacroStorage.ensure_dir()
        path = os.path.join(MACROS_DIR, "macro_order.json")
        with open(path, 'w') as f:
            json.dump(macro_ids, f)
    
    @staticmethod
    def delete(macro_id: str):
        """Delete macro"""
        path = MacroStorage.get_path(macro_id)
        if os.path.exists(path):
            os.remove(path)
            print(f"[MacroStorage] Deleted macro: {macro_id}")
