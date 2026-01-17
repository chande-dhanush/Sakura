"""
Sakura V16: Reactive Identity Manager & Event Bus
=================================================
Singleton identity that syncs with user_settings.json and broadcasts changes.

Features:
- Reactive identity refresh (not just load-on-restart)
- Event bus for cross-module synchronization
- WorldGraph integration
"""
import os
import json
import threading
from typing import Dict, Any, Callable, List
from datetime import datetime


# =============================================================================
# EVENT BUS - Cross-module synchronization
# =============================================================================

class EventBus:
    """
    Simple event bus for broadcasting identity/state changes.
    
    V16: Prevents "Zombie Identity" where RAM is stale vs disk.
    """
    _instance = None
    _lock = threading.RLock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        self._listeners: Dict[str, List[Callable]] = {}
        self._initialized = True
    
    def subscribe(self, event: str, callback: Callable) -> None:
        """Subscribe to an event."""
        if event not in self._listeners:
            self._listeners[event] = []
        if callback not in self._listeners[event]:
            self._listeners[event].append(callback)
    
    def unsubscribe(self, event: str, callback: Callable) -> None:
        """Unsubscribe from an event."""
        if event in self._listeners and callback in self._listeners[event]:
            self._listeners[event].remove(callback)
    
    def emit(self, event: str, data: Any = None) -> None:
        """Emit an event to all subscribers."""
        if event in self._listeners:
            for callback in self._listeners[event]:
                try:
                    callback(data)
                except Exception as e:
                    print(f"⚠️ [EventBus] Listener error for '{event}': {e}")


# Singleton accessor
_event_bus: EventBus = None

def get_event_bus() -> EventBus:
    """Get singleton EventBus instance."""
    global _event_bus
    if _event_bus is None:
        _event_bus = EventBus()
    return _event_bus


# =============================================================================
# IDENTITY MANAGER - Reactive identity state
# =============================================================================

class IdentityManager:
    """
    V16: Centralized identity management with reactive updates.
    
    - Loads from user_settings.json
    - Broadcasts changes via EventBus
    - Provides deterministic identity lookup (no LLM required)
    """
    _instance = None
    _lock = threading.RLock()
    
    # Event names
    IDENTITY_CHANGED = "identity:changed"
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._identity: Dict[str, Any] = {
            "name": "User",
            "location": "",
            "bio": "",
            "age": None,
            "birthday": "",
            "interests": [],
            "not_claims": ["NOT a public figure", "NOT a celebrity"],
        }
        self._last_load_time: datetime = None
        self._settings_path: str = None
        
        # Load on init
        self._load_settings()
        self._initialized = True
    
    def _get_settings_path(self) -> str:
        """Get path to user_settings.json."""
        if self._settings_path:
            return self._settings_path
        
        from ..utils.pathing import get_project_root
        self._settings_path = os.path.join(get_project_root(), "data", "user_settings.json")
        return self._settings_path
    
    def _load_settings(self) -> bool:
        """Load identity from user_settings.json."""
        path = self._get_settings_path()
        
        if not os.path.exists(path):
            print(f"⚠️ [IdentityManager] No user_settings.json found")
            return False
        
        try:
            with open(path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Map settings keys to identity keys
            if data.get("user_name"):
                self._identity["name"] = data["user_name"]
            if data.get("user_location"):
                self._identity["location"] = data["user_location"]
            if data.get("user_bio"):
                self._identity["bio"] = data["user_bio"]
            if data.get("age"):
                self._identity["age"] = data["age"]
            if data.get("birthday"):
                self._identity["birthday"] = data["birthday"]
            if data.get("interests"):
                self._identity["interests"] = data["interests"]
            
            self._last_load_time = datetime.now()
            print(f"✅ [IdentityManager] Loaded identity: {self._identity['name']}")
            return True
            
        except Exception as e:
            print(f"❌ [IdentityManager] Load failed: {e}")
            return False
    
    def refresh(self) -> None:
        """
        Reload identity from disk and broadcast change.
        
        Called by:
        - /setup endpoint after saving
        - File watcher (if implemented)
        """
        old_name = self._identity.get("name")
        self._load_settings()
        
        # Broadcast if changed
        if self._identity.get("name") != old_name:
            get_event_bus().emit(self.IDENTITY_CHANGED, self._identity.copy())
            print(f"📢 [IdentityManager] Broadcasted identity change")
    
    def update_and_save(self, updates: Dict[str, Any]) -> bool:
        """
        Update identity and persist to disk.
        
        Args:
            updates: Dict of fields to update
            
        Returns:
            True if saved successfully
        """
        path = self._get_settings_path()
        
        # Ensure directory exists
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        # Load existing
        existing = {}
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    existing = json.load(f)
            except:
                pass
        
        # Map identity keys to settings keys
        key_map = {
            "name": "user_name",
            "location": "user_location",
            "bio": "user_bio",
            "age": "age",
            "birthday": "birthday",
            "interests": "interests",
        }
        
        # Apply updates
        for key, value in updates.items():
            if key in key_map and value:
                existing[key_map[key]] = value
                self._identity[key] = value
        
        # Save
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(existing, f, indent=2)
            
            # Broadcast change
            get_event_bus().emit(self.IDENTITY_CHANGED, self._identity.copy())
            print(f"💾 [IdentityManager] Saved and broadcasted identity update")
            return True
            
        except Exception as e:
            print(f"❌ [IdentityManager] Save failed: {e}")
            return False
    
    # =========================================================================
    # DETERMINISTIC LOOKUPS (for self-check, no LLM required)
    # =========================================================================
    
    @property
    def name(self) -> str:
        return self._identity.get("name", "User")
    
    @property
    def location(self) -> str:
        return self._identity.get("location", "")
    
    @property
    def bio(self) -> str:
        return self._identity.get("bio", "")
    
    @property
    def not_claims(self) -> List[str]:
        return self._identity.get("not_claims", [])
    
    def get_identity_dict(self) -> Dict[str, Any]:
        """Get full identity as dict."""
        return self._identity.copy()
    
    def get_summary(self) -> str:
        """Generate natural language summary."""
        parts = [f"{self.name}"]
        
        if self._identity.get("age"):
            parts.append(f"{self._identity['age']}")
        
        if self.location:
            parts.append(f"from {self.location}")
        
        if self._identity.get("interests"):
            interests = ", ".join(self._identity["interests"][:3])
            parts.append(f"Interests: {interests}")
        
        return ". ".join(parts) + "."
    
    def check_claim(self, response: str) -> tuple:
        """
        V16: DETERMINISTIC self-check (no LLM, just regex/lookup).
        
        Args:
            response: The generated response text
            
        Returns:
            (is_valid, violation_message) - (True, None) if valid
        """
        import re
        response_lower = response.lower()
        
        # Check 1: NOT claims (e.g., "NOT a public figure")
        for not_claim in self.not_claims:
            # Extract the negated concept
            if "not " in not_claim.lower():
                concept = not_claim.lower().replace("not ", "").replace("a ", "").strip()
                # Check if response claims the opposite
                claim_patterns = [
                    f"you are {concept}",
                    f"you're {concept}",
                    f"you are a {concept}",
                    f"you're a {concept}",
                    f"you are the {concept}",
                ]
                for pattern in claim_patterns:
                    if pattern in response_lower:
                        return False, f"Response violates NOT claim: {not_claim}"
        
        # Check 2: Location mismatch
        if self.location:
            location_claim = re.search(r"you (?:live in|are from|'re from) (\w+)", response_lower)
            if location_claim:
                claimed = location_claim.group(1)
                if claimed.lower() not in self.location.lower():
                    return False, f"Location mismatch: claimed '{claimed}', actual '{self.location}'"
        
        # Check 3: Name mismatch (if response claims a different name)
        name_claim = re.search(r"your name is (\w+)", response_lower)
        if name_claim:
            claimed = name_claim.group(1)
            if claimed.lower() != self.name.lower():
                return False, f"Name mismatch: claimed '{claimed}', actual '{self.name}'"
        
        return True, None


# Singleton accessor
_identity_manager: IdentityManager = None

def get_identity_manager() -> IdentityManager:
    """Get singleton IdentityManager instance."""
    global _identity_manager
    if _identity_manager is None:
        _identity_manager = IdentityManager()
    return _identity_manager
