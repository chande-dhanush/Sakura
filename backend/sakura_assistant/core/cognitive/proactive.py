"""
Sakura V15: Proactive Scheduler (The Nervous System)
=====================================================
Enables Sakura to initiate conversations when lonely.

Key constraints:
- Silence is the default (only initiates if loneliness > 0.85)
- Rate limited (max 1 per day)
- Time of day aware (9 AM - 9 PM only)
- Uses pre-computed messages (zero daytime LLM cost)
"""

import json
import os
import time
import asyncio
from datetime import datetime
from typing import Optional, List, Dict, Any, Callable

from .desire import get_desire_system, DesireSystem


class ProactiveScheduler:
    """
    The "Motor Cortex" - decides when to reach out.
    
    Uses pre-computed messages from planned_initiations.json
    to achieve zero-cost proactive messages during daytime.
    """
    
    _instance: Optional["ProactiveScheduler"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
            
        self.desire_system: DesireSystem = get_desire_system()
        self.initiations_path: Optional[str] = None
        self.backoff_path: Optional[str] = None
        self.failed_count: int = 0
        self.websocket_callback: Optional[Callable] = None
        self._running = False
        self._initialized = True
    
    def initialize(self, initiations_path: str, websocket_callback: Callable = None):
        """
        Initialize with paths and optional WebSocket callback.
        
        Args:
            initiations_path: Path to planned_initiations.json
            websocket_callback: async function(message: str) to send proactive messages
        """
        self.initiations_path = initiations_path
        self.backoff_path = os.path.join(os.path.dirname(initiations_path), "proactive_backoff.json")
        self.websocket_callback = websocket_callback
        self._load_backoff()
        print(f" [ProactiveScheduler] Initialized")

    def _load_backoff(self):
        """Restore failed initiation backoff state."""
        if not self.backoff_path or not os.path.exists(self.backoff_path):
            self.failed_count = 0
            return
        try:
            with open(self.backoff_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.failed_count = int(data.get("failed_count", 0))
        except Exception as e:
            print(f"   [ProactiveScheduler] Failed to load backoff: {e}")
            self.failed_count = 0

    def _save_backoff(self):
        """Persist failed initiation backoff state."""
        if not self.backoff_path:
            return
        try:
            os.makedirs(os.path.dirname(self.backoff_path), exist_ok=True)
            with open(self.backoff_path, "w", encoding="utf-8") as f:
                json.dump({
                    "failed_count": self.failed_count,
                    "last_updated": datetime.now().isoformat()
                }, f, indent=2)
        except Exception as e:
            print(f"   [ProactiveScheduler] Failed to save backoff: {e}")

    def _increment_failed_initiation(self, reason: str):
        """Record a failed proactive initiation attempt."""
        self.failed_count += 1
        self._save_backoff()
        print(f"   [ProactiveScheduler] Failed initiation #{self.failed_count}: {reason}")
    
    def get_planned_initiations(self) -> List[str]:
        """Load pre-computed messages from JSON."""
        if not self.initiations_path or not os.path.exists(self.initiations_path):
            return []
        
        try:
            with open(self.initiations_path, "r") as f:
                data = json.load(f)
                return data.get("messages", [])
        except Exception as e:
            print(f"   [ProactiveScheduler] Failed to load initiations: {e}")
            return []
    
    def pop_initiation(self) -> Optional[str]:
        """
        Pop one pre-computed message (removes from file).
        Returns None if no messages available.
        """
        messages = self.get_planned_initiations()
        if not messages:
            return None
        
        # Pop first message
        message = messages.pop(0)
        
        # Save remaining messages
        try:
            os.makedirs(os.path.dirname(self.initiations_path), exist_ok=True)
            with open(self.initiations_path, "w") as f:
                json.dump({"messages": messages, "updated": datetime.now().isoformat()}, f, indent=2)
        except Exception as e:
            print(f"   [ProactiveScheduler] Failed to save: {e}")
        
        return message
    
    async def check_and_initiate(self) -> bool:
        """
        Hourly check: Should Sakura reach out?
        
        V15.2.1: Now respects ui_visible state (Bubble-Gate logic).
        
        Returns True if initiation occurred.
        """
        # V15.2.1: Import shared state
        from .state import get_proactive_state
        state = get_proactive_state()
        
        # Gate 0: Check if UI is visible (Bubble-Gate)
        if not state.ui_visible:
            # User has hidden the bubble - queue the message for later
            should_act, reason = self.desire_system.should_initiate()
            if should_act:
                message = self.pop_initiation()
                if message:
                    state.queue_message(message)
                    print(f" [ProactiveScheduler] UI hidden, message queued for later")
                    return False
            print(f" [ProactiveScheduler] UI hidden, staying silent")
            return False
        
        # Gate 1: Check desire system
        should_act, reason = self.desire_system.should_initiate()
        
        if not should_act:
            print(f" [ProactiveScheduler] Staying silent: {reason}")
            return False
        
        # Gate 2: Get pre-computed message
        message = self.pop_initiation()
        
        if not message:
            print(" [ProactiveScheduler] No pre-computed messages available")
            self._increment_failed_initiation("no_precomputed_message")
            return False
        
        # Gate 3: Send via WebSocket
        if self.websocket_callback:
            try:
                await self.websocket_callback(message)
                self.desire_system.record_initiation()
                print(f" [ProactiveScheduler] Sent: {message[:50]}...")
                return True
            except Exception as e:
                print(f" [ProactiveScheduler] WebSocket send failed: {e}")
                self._increment_failed_initiation("websocket_send_failed")
                return False
        else:
            # No WebSocket callback - just log
            print(f" [ProactiveScheduler] Would send (no WS): {message[:50]}...")
            self.desire_system.record_initiation()
            return True
    
    def save_planned_initiations(self, messages: List[str]):
        """
        Save pre-computed messages (called by nightly job).
        """
        if not self.initiations_path:
            print("   [ProactiveScheduler] No path configured")
            return
        
        try:
            os.makedirs(os.path.dirname(self.initiations_path), exist_ok=True)
            with open(self.initiations_path, "w") as f:
                json.dump({
                    "messages": messages,
                    "generated": datetime.now().isoformat(),
                    "count": len(messages)
                }, f, indent=2)
            print(f" [ProactiveScheduler] Saved {len(messages)} planned initiations")
        except Exception as e:
            print(f" [ProactiveScheduler] Failed to save: {e}")
    
    def get_status(self) -> Dict[str, Any]:
        """Get current status for debugging."""
        messages = self.get_planned_initiations()
        should_act, reason = self.desire_system.should_initiate()
        
        return {
            "pending_messages": len(messages),
            "should_initiate": should_act,
            "reason": reason,
            "failed_count": self.failed_count,
            "desire_state": self.desire_system.get_state().to_dict()
        }


#                                                                                
# SINGLETON ACCESSOR
#                                                                                

_proactive_scheduler: Optional[ProactiveScheduler] = None


def get_proactive_scheduler() -> ProactiveScheduler:
    """Get the global ProactiveScheduler instance."""
    global _proactive_scheduler
    if _proactive_scheduler is None:
        _proactive_scheduler = ProactiveScheduler()
    return _proactive_scheduler
