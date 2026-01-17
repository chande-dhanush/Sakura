"""
Sakura V15.2.2: Shared Cognitive State
======================================
Centralized state for UI visibility and pending proactive messages.

V15.2.2 "Peace Treaty" Update:
- Added RLock for thread-safe visibility/queue operations
- Prevents TOCTOU race conditions between scheduler and frontend

This module exists to avoid circular imports between server.py and proactive.py.
Both modules import from here to share state.
"""

import json
import os
import time
import threading
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════════════════════════

TTL_SECONDS: int = 2 * 60 * 60  # 2 hours - messages older than this are discarded


# ═══════════════════════════════════════════════════════════════════════════════
# STATE DATACLASS
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ProactiveState:
    """
    Centralized state for the proactive notification system.
    
    V15.2.2: Thread-safe with RLock to prevent TOCTOU race conditions.
    
    Attributes:
        ui_visible: Whether the UI bubble is currently visible to the user.
                    When False, proactive messages are queued instead of sent.
        pending_initiation: A queued proactive message waiting to be delivered.
                           Contains 'content' (str) and 'timestamp' (float).
        failed_initiation_count: Number of failed initiations (persisted across restarts).
    """
    ui_visible: bool = True
    pending_initiation: Optional[Dict[str, Any]] = None
    failed_initiation_count: int = 0
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    
    def __post_init__(self):
        # Load persisted backoff state on init
        self._load_persistent_state()
    
    def queue_message(self, content: str) -> None:
        """
        Queue a proactive message for later delivery.
        Thread-safe: Uses RLock to prevent race conditions.
        """
        with self._lock:
            self.pending_initiation = {
                "content": content,
                "timestamp": time.time()
            }
            print(f"🤫 [State] Message queued: {content[:50]}...")
    
    def pop_pending_message(self) -> Optional[str]:
        """
        Retrieve and clear the pending message if it's still valid (within TTL).
        Thread-safe: Uses RLock.
        """
        with self._lock:
            if self.pending_initiation is None:
                return None
            
            content = self.pending_initiation["content"]
            timestamp = self.pending_initiation["timestamp"]
            age_seconds = time.time() - timestamp
            
            # Clear the pending message regardless of TTL
            self.pending_initiation = None
            
            # Check TTL
            if age_seconds > TTL_SECONDS:
                age_hours = age_seconds / 3600
                print(f"🗑️ [State] Message expired ({age_hours:.1f}h old, TTL={TTL_SECONDS/3600}h)")
                self.on_message_expired()
                return None
            
            print(f"📬 [State] Delivering queued message ({age_seconds/60:.1f}m old)")
            return content
    
    def set_visibility(self, visible: bool) -> Optional[str]:
        """
        Update visibility state. Thread-safe: Uses RLock.
        If transitioning to visible and there's a pending message, return it.
        """
        with self._lock:
            was_visible = self.ui_visible
            self.ui_visible = visible
            
            print(f"👁️ [State] Visibility: {was_visible} → {visible}")
            
            # If becoming visible, check for pending messages
            if visible and not was_visible:
                return self._pop_pending_unlocked()
            
            return None
    
    def _pop_pending_unlocked(self) -> Optional[str]:
        """Internal: Pop pending message without acquiring lock (called from set_visibility)."""
        if self.pending_initiation is None:
            return None
        
        content = self.pending_initiation["content"]
        timestamp = self.pending_initiation["timestamp"]
        age_seconds = time.time() - timestamp
        self.pending_initiation = None
        
        if age_seconds > TTL_SECONDS:
            self.on_message_expired()
            return None
        
        return content
    
    def on_message_expired(self) -> None:
        """Track failed initiation for exponential backoff."""
        self.failed_initiation_count += 1
        self._save_persistent_state()
        print(f"📉 [State] Failed initiation #{self.failed_initiation_count}")
    
    def on_successful_interaction(self) -> None:
        """Reset backoff counter on successful user interaction."""
        if self.failed_initiation_count > 0:
            self.failed_initiation_count = 0
            self._save_persistent_state()
            print("✅ [State] Backoff counter reset")
    
    def _get_state_path(self) -> str:
        """Get path for persisted state file."""
        from sakura_assistant.config import get_project_root
        return os.path.join(get_project_root(), "data", "proactive_backoff.json")
    
    def _load_persistent_state(self) -> None:
        """Load backoff state from disk."""
        try:
            path = self._get_state_path()
            if os.path.exists(path):
                with open(path, "r") as f:
                    data = json.load(f)
                    self.failed_initiation_count = data.get("failed_count", 0)
                    print(f"📂 [State] Loaded backoff state: {self.failed_initiation_count} failures")
        except Exception as e:
            print(f"⚠️ [State] Failed to load backoff state: {e}")
    
    def _save_persistent_state(self) -> None:
        """Save backoff state to disk."""
        try:
            path = self._get_state_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                json.dump({"failed_count": self.failed_initiation_count}, f)
        except Exception as e:
            print(f"⚠️ [State] Failed to save backoff state: {e}")


# ═══════════════════════════════════════════════════════════════════════════════
# SINGLETON INSTANCE
# ═══════════════════════════════════════════════════════════════════════════════

# Global state instance - imported by both server.py and proactive.py
_state: Optional[ProactiveState] = None


def get_proactive_state() -> ProactiveState:
    """Get the global ProactiveState instance."""
    global _state
    if _state is None:
        _state = ProactiveState()
        print("🧠 [State] ProactiveState initialized")
    return _state
