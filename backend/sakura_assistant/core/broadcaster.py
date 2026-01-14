"""
Sakura V12 Broadcaster
======================
Generic singleton for broadcasting real-time "Thought Stream" events to the frontend.
Handles WebSocket connections (simulated for now) and event distribution.
"""
from typing import Dict, Any, List, Callable
import json
import time

class Broadcaster:
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(Broadcaster, cls).__new__(cls)
            cls._instance.listeners = []
        return cls._instance

    def add_listener(self, callback: Callable[[str, Dict], None]):
        """Register a callback to receive events."""
        self.listeners.append(callback)

    def broadcast(self, event: str, data: Dict[str, Any]):
        """
        Broadcast an event to all listeners.
        
        Args:
            event: Event name (e.g., "rate_limit", "thinking", "research_start")
            data: Payload data
        """
        # Add timestamp if missing
        if "timestamp" not in data:
            data["timestamp"] = time.time()
            
        # Log to console for dev visibility
        emoji_map = {
            "rate_limit": "⏳",
            "thinking": "🧠",
            "tool_start": "🛠️",
            "research_start": "🕵️",
            "cache_hit": "⚡",
        }
        icon = emoji_map.get(event, "📡")
        
        # print(f"{icon} [BROADCAST] {event}: {json.dumps(data)}")
        
        # Notify listeners (e.g., WebSocket manager)
        for listener in self.listeners:
            try:
                listener(event, data)
            except Exception as e:
                print(f"⚠️ Broadcast listener error: {e}")

# Singleton accessor
def get_broadcaster():
    return Broadcaster()

# Convenience function
def broadcast(event: str, data: Dict[str, Any]):
    get_broadcaster().broadcast(event, data)
