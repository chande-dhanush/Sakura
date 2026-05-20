import time
import json
from typing import Dict, Any, List
from ..database import Database, get_db_connection

class PreferenceAdaptationEngine:
    """
    Preference Adaptation & Forgetting Engine (Step 8)
    ==================================================
    Manages temporal behavior learning, habits, user preferences,
    and decay/forgetting logic for stale memory entities.
    """
    
    def __init__(self):
        self.pref_key = "user_preferences_learning"
        self._load_preferences()

    def _load_preferences(self):
        default_prefs = {
            "focus_hours": [9, 10, 11, 14, 15, 16], # hour integers
            "preferred_verbosity": "NORMAL",
            "preferred_tone": "neutral",
            "habit_transitions": {} # map app -> next_app counts
        }
        try:
            self.prefs = Database.get_setting(self.pref_key, default_prefs)
        except Exception:
            self.prefs = default_prefs
            
        for k, v in default_prefs.items():
            if k not in self.prefs:
                self.prefs[k] = v

    def save_preferences(self):
        try:
            Database.set_setting(self.pref_key, self.prefs)
        except Exception as e:
            print(f"⚠️ [PreferenceAdaptationEngine] Failed to save preferences: {e}")

    def learn_focus_hours(self, hour: int):
        """Record activity times to learn when the user is most active/focused."""
        if hour not in self.prefs["focus_hours"]:
            self.prefs["focus_hours"].append(hour)
            self.save_preferences()

    def record_app_transition(self, from_app: str, to_app: str):
        """Learn application transition habits."""
        if not from_app or not to_app or from_app == to_app:
            return
        key = f"{from_app}->{to_app}"
        self.prefs["habit_transitions"][key] = self.prefs["habit_transitions"].get(key, 0) + 1
        self.save_preferences()

    @staticmethod
    def run_forgetting_decay():
        """
        Runs forgetting decay logic:
        - Decays familiarity of WorldGraph entities.
        - Removes ephemeral entities that have familiarity < 0.1 and haven't been referenced recently.
        """
        try:
            conn = get_db_connection()
            # 1. Decay familiarity of all entities by 5%
            conn.execute("UPDATE entities SET familiarity = familiarity * 0.95")
            
            # 2. Prune ephemeral entities with familiarity < 0.1 and lifecycle = 'ephemeral'
            conn.execute(
                "DELETE FROM entities WHERE lifecycle = 'ephemeral' AND familiarity < 0.1"
            )
            conn.commit()
            print("🍂 [ForgettingEngine] Memory decay and ephemeral pruning executed successfully.")
        except Exception as e:
            print(f"⚠️ [ForgettingEngine] Decay run failed: {e}")
