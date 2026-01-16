"""
Sakura V15.2: Shared Cognitive State
====================================
Centralized state for UI visibility and pending proactive messages.

This module exists to avoid circular imports between server.py and proactive.py.
Both modules import from here to share state.

Design Decision:
- We use module-level state instead of a class to keep it simple
- State is NOT persisted to disk (acceptable for single-session use)
- TTL_SECONDS controls how long a queued message remains valid
"""

import time
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
    
    Attributes:
        ui_visible: Whether the UI bubble is currently visible to the user.
                    When False, proactive messages are queued instead of sent.
        pending_initiation: A queued proactive message waiting to be delivered.
                           Contains 'content' (str) and 'timestamp' (float).
    """
    ui_visible: bool = True  # Default True = assume user can see messages
    pending_initiation: Optional[Dict[str, Any]] = None
    
    def queue_message(self, content: str) -> None:
        """
        Queue a proactive message for later delivery.
        Called when ui_visible is False.
        """
        self.pending_initiation = {
            "content": content,
            "timestamp": time.time()
        }
        print(f"🤫 [State] Message queued: {content[:50]}...")
    
    def pop_pending_message(self) -> Optional[str]:
        """
        Retrieve and clear the pending message if it's still valid (within TTL).
        Returns None if no message or if message has expired.
        """
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
            return None
        
        print(f"📬 [State] Delivering queued message ({age_seconds/60:.1f}m old)")
        return content
    
    def set_visibility(self, visible: bool) -> Optional[str]:
        """
        Update visibility state.
        If transitioning to visible and there's a pending message, return it.
        
        Returns:
            The pending message content if transitioning to visible and message is valid.
            None otherwise.
        """
        was_visible = self.ui_visible
        self.ui_visible = visible
        
        print(f"👁️ [State] Visibility: {was_visible} → {visible}")
        
        # If becoming visible, check for pending messages
        if visible and not was_visible:
            return self.pop_pending_message()
        
        return None


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
