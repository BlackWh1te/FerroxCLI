import json
import os
from typing import List, Dict, Optional

class HistoryManager:
    """Manages chat history persistence and retrieval."""
    def __init__(self, history_file: str = os.path.expanduser("~/.ferrox/history.json")):
        self.history_file = history_file
        self.history: List[Dict] = []
        self._load()

    def _load(self):
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, 'r') as f:
                    self.history = json.load(f)
            except:
                self.history = []

    def save(self):
        os.makedirs(os.path.dirname(self.history_file), exist_ok=True)
        with open(self.history_file, 'w') as f:
            json.dump(self.history, f, indent=2)

    def add(self, role: str, content: str, metadata: Optional[Dict] = None):
        msg = {"role": role, "content": content}
        if metadata:
            msg["metadata"] = metadata
        self.history.append(msg)
        self.save()

    def get_all(self):
        return self.history

    def get_search_count(self) -> int:
        """Count how many times web_search tool was used."""
        count = 0
        for msg in self.history:
            if msg.get("role") == "tool" and msg.get("name") == "web_search":
                count += 1
        return count
