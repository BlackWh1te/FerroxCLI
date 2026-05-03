"""Conversation memory system for Ferrox agent.

Provides long-term conversation storage with vector embeddings, semantic search,
context window optimization, and user preference learning.
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, asdict
from collections import defaultdict

# Import tracer
from opentelemetry import trace
tracer = trace.get_tracer(__name__)


@dataclass
class MemoryEntry:
    """A single conversation memory entry."""
    timestamp: str
    role: str  # "user" or "assistant"
    content: str
    embedding: Optional[List[float]] = None
    metadata: Optional[Dict[str, Any]] = None
    summary: Optional[str] = None  # Summarized version for context optimization


class ConversationMemory:
    """Manages conversation memory with vector search and context optimization."""
    
    def __init__(self, memory_dir: Optional[Path] = None):
        """Initialize conversation memory.
        
        Args:
            memory_dir: Directory to store memory files (defaults to ~/.ferrox/memory)
        """
        if memory_dir is None:
            memory_dir = Path.home() / ".ferrox" / "memory"
        
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        self.conversations_file = self.memory_dir / "conversations.json"
        self.embeddings_file = self.memory_dir / "embeddings.faiss"
        self.preferences_file = self.memory_dir / "preferences.json"
        
        self.entries: List[MemoryEntry] = []
        self.preferences: Dict[str, Any] = {
            "coding_style": {},
            "preferred_patterns": [],
            "frequent_commands": defaultdict(int),
            "project_contexts": defaultdict(int)
        }
        
        # Load existing data
        self._load_conversations()
        self._load_preferences()
        
        # Initialize embedding model (lazy load)
        self._embedding_model = None
        self._faiss_index = None
    
    def _get_embedding_model(self):
        """Lazy load the sentence transformer model."""
        if self._embedding_model is None:
            try:
                from sentence_transformers import SentenceTransformer
                self._embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            except ImportError:
                print("Warning: sentence-transformers not installed. Semantic search disabled.")
                return None
        return self._embedding_model
    
    def _get_embedding(self, text: str) -> Optional[List[float]]:
        """Get embedding for text."""
        model = self._get_embedding_model()
        if model is None:
            return None
        return model.encode(text).tolist()
    
    def add_entry(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        """Add a new entry to conversation memory.
        
        Args:
            role: "user" or "assistant"
            content: The message content
            metadata: Optional metadata (e.g., project, tool used, etc.)
        """
        with tracer.start_as_current_span("memory_add_entry") as span:
            span.set_attribute("role", role)
            span.set_attribute("content_length", len(content))
            
            entry = MemoryEntry(
                timestamp=datetime.now().isoformat(),
                role=role,
                content=content,
                embedding=self._get_embedding(content),
                metadata=metadata or {}
            )
            
            self.entries.append(entry)
            self._update_preferences(role, content, metadata)
            self._save_conversations()
    
    def _update_preferences(self, role: str, content: str, metadata: Dict[str, Any]) -> None:
        """Update user preferences based on conversation."""
        # Track frequent commands
        if metadata and "command" in metadata:
            self.preferences["frequent_commands"][metadata["command"]] += 1
        
        # Track project contexts
        if metadata and "project" in metadata:
            self.preferences["project_contexts"][metadata["project"]] += 1
        
        # Track coding patterns (simplified)
        if role == "user":
            # Detect coding style preferences
            if "use tabs" in content.lower():
                self.preferences["coding_style"]["indentation"] = "tabs"
            elif "use spaces" in content.lower():
                self.preferences["coding_style"]["indentation"] = "spaces"
            
            # Detect preferred patterns
            if "test" in content.lower():
                self.preferences["preferred_patterns"].append("testing")
            if "document" in content.lower():
                self.preferences["preferred_patterns"].append("documentation")
        
        # Keep only last 100 patterns
        if len(self.preferences["preferred_patterns"]) > 100:
            self.preferences["preferred_patterns"] = self.preferences["preferred_patterns"][-100:]
    
    def semantic_search(self, query: str, top_k: int = 5, role_filter: Optional[str] = None) -> List[MemoryEntry]:
        """Search conversation history semantically.
        
        Args:
            query: Search query
            top_k: Number of results to return
            role_filter: Optional filter by role ("user" or "assistant")
        
        Returns:
            List of matching memory entries
        """
        with tracer.start_as_current_span("memory_semantic_search") as span:
            span.set_attribute("query", query)
            span.set_attribute("top_k", top_k)
            
            model = self._get_embedding_model()
            if model is None:
                # Fallback to keyword search
                return self._keyword_search(query, top_k, role_filter)
            
            query_embedding = model.encode(query)
            
            # Filter entries
            candidates = self.entries
            if role_filter:
                candidates = [e for e in candidates if e.role == role_filter]
            
            # Compute similarities
            similarities = []
            for entry in candidates:
                if entry.embedding:
                    import numpy as np
                    similarity = float(np.dot(query_embedding, entry.embedding) / 
                                    (np.linalg.norm(query_embedding) * np.linalg.norm(entry.embedding)))
                    similarities.append((similarity, entry))
            
            # Sort by similarity and return top_k
            similarities.sort(key=lambda x: x[0], reverse=True)
            return [entry for _, entry in similarities[:top_k]]
    
    def _keyword_search(self, query: str, top_k: int, role_filter: Optional[str] = None) -> List[MemoryEntry]:
        """Fallback keyword search when embeddings are not available."""
        query_lower = query.lower()
        candidates = self.entries
        if role_filter:
            candidates = [e for e in candidates if e.role == role_filter]
        
        # Simple keyword matching
        scored = []
        for entry in candidates:
            score = sum(1 for word in query_lower.split() if word in entry.content.lower())
            if score > 0:
                scored.append((score, entry))
        
        scored.sort(key=lambda x: x[0], reverse=True)
        return [entry for _, entry in scored[:top_k]]
    
    def get_recent_context(self, max_entries: int = 10, max_tokens: int = 4000) -> List[Dict[str, str]]:
        """Get recent conversation context with token optimization.
        
        Args:
            max_entries: Maximum number of recent entries to include
            max_tokens: Maximum tokens to include (uses summarization for older entries)
        
        Returns:
            List of message dictionaries for LLM context
        """
        with tracer.start_as_current_span("memory_get_recent_context") as span:
            span.set_attribute("max_entries", max_entries)
            span.set_attribute("max_tokens", max_tokens)
            
            if not self.entries:
                return []
            
            # Get recent entries
            recent = self.entries[-max_entries:]
            
            # Estimate tokens (rough approximation: 1 token ≈ 4 characters)
            total_chars = sum(len(e.content) for e in recent)
            estimated_tokens = total_chars // 4
            
            if estimated_tokens <= max_tokens:
                # No summarization needed
                return [{"role": e.role, "content": e.content} for e in recent]
            
            # Need to summarize older entries
            result = []
            current_tokens = 0
            summary_buffer = []
            
            for entry in reversed(recent):
                entry_tokens = len(entry.content) // 4
                
                if current_tokens + entry_tokens > max_tokens:
                    # Summarize buffered entries
                    if summary_buffer:
                        summary = self._summarize_entries(summary_buffer)
                        if summary:
                            result.insert(0, {"role": "system", "content": f"[Previous conversation summary]: {summary}"})
                        summary_buffer = []
                    
                    # Keep most recent entry even if it exceeds limit
                    result.insert(0, {"role": entry.role, "content": entry.content})
                    break
                
                result.insert(0, {"role": entry.role, "content": entry.content})
                current_tokens += entry_tokens
                summary_buffer.append(entry)
            
            return result
    
    def _summarize_entries(self, entries: List[MemoryEntry]) -> str:
        """Summarize a list of conversation entries."""
        if not entries:
            return ""
        
        # Simple summarization: extract key topics
        user_messages = [e.content for e in entries if e.role == "user"]
        assistant_messages = [e.content for e in entries if e.role == "assistant"]
        
        summary_parts = []
        if user_messages:
            summary_parts.append(f"User discussed: {', '.join(user_messages[:3])}")
        if assistant_messages:
            summary_parts.append(f"Assistant provided: {len(assistant_messages)} responses")
        
        return " | ".join(summary_parts)
    
    def get_preferences(self) -> Dict[str, Any]:
        """Get learned user preferences."""
        return {
            "coding_style": dict(self.preferences["coding_style"]),
            "preferred_patterns": self.preferences["preferred_patterns"],
            "frequent_commands": dict(self.preferences["frequent_commands"]),
            "project_contexts": dict(self.preferences["project_contexts"])
        }
    
    def clear_old_entries(self, days_to_keep: int = 30) -> int:
        """Clear entries older than specified days.
        
        Args:
            days_to_keep: Number of days to keep entries
        
        Returns:
            Number of entries removed
        """
        with tracer.start_as_current_span("memory_clear_old_entries") as span:
            span.set_attribute("days_to_keep", days_to_keep)
            
            from datetime import datetime, timedelta
            cutoff = datetime.now() - timedelta(days=days_to_keep)
            
            original_count = len(self.entries)
            self.entries = [e for e in self.entries 
                          if datetime.fromisoformat(e.timestamp) > cutoff]
            
            removed = original_count - len(self.entries)
            if removed > 0:
                self._save_conversations()
            
            return removed
    
    def _load_conversations(self) -> None:
        """Load conversations from disk."""
        if self.conversations_file.exists():
            try:
                with open(self.conversations_file, 'r') as f:
                    data = json.load(f)
                    self.entries = [MemoryEntry(**e) for e in data]
            except Exception as e:
                print(f"Error loading conversations: {e}")
    
    def _save_conversations(self) -> None:
        """Save conversations to disk."""
        try:
            with open(self.conversations_file, 'w') as f:
                json.dump([asdict(e) for e in self.entries], f, indent=2)
        except Exception as e:
            print(f"Error saving conversations: {e}")
    
    def _load_preferences(self) -> None:
        """Load preferences from disk."""
        if self.preferences_file.exists():
            try:
                with open(self.preferences_file, 'r') as f:
                    data = json.load(f)
                    self.preferences.update(data)
                    # Convert back to defaultdict
                    self.preferences["frequent_commands"] = defaultdict(int, data.get("frequent_commands", {}))
                    self.preferences["project_contexts"] = defaultdict(int, data.get("project_contexts", {}))
            except Exception as e:
                print(f"Error loading preferences: {e}")
    
    def _save_preferences(self) -> None:
        """Save preferences to disk."""
        try:
            # Convert defaultdict to dict for JSON serialization
            data = {
                "coding_style": self.preferences["coding_style"],
                "preferred_patterns": self.preferences["preferred_patterns"],
                "frequent_commands": dict(self.preferences["frequent_commands"]),
                "project_contexts": dict(self.preferences["project_contexts"])
            }
            with open(self.preferences_file, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            print(f"Error saving preferences: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get memory statistics."""
        return {
            "total_entries": len(self.entries),
            "user_entries": sum(1 for e in self.entries if e.role == "user"),
            "assistant_entries": sum(1 for e in self.entries if e.role == "assistant"),
            "with_embeddings": sum(1 for e in self.entries if e.embedding),
            "oldest_entry": self.entries[0].timestamp if self.entries else None,
            "newest_entry": self.entries[-1].timestamp if self.entries else None,
            "preferences": self.get_preferences()
        }
