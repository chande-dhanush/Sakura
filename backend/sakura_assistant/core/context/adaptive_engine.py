import time
import re
from datetime import datetime
from typing import Dict, Any, List
from ..database import Database

class AdaptiveInteractionEngine:
    """
    Adaptive Interaction Engine (Phase A / Step 1)
    =============================================
    Tracks interaction density, verbosity preference, tone, late-night usage,
    and interruption frequency, then selects the appropriate Response Posture.
    """
    
    def __init__(self):
        self.metrics_key = "interaction_metrics"
        self._load_metrics()

    def _load_metrics(self):
        default_metrics = {
            "query_lengths": [],        # list of recent query word counts
            "response_lengths": [],     # list of recent response word counts
            "inter_request_delays": [], # list of delay seconds between commands
            "interruption_count": 0,    # number of times generation was cancelled
            "ignored_responses_count": 0,
            "corrections_count": 0,     # user corrected the assistant
            "last_request_time": 0.0,
            "preferred_tone": "neutral", # adapted tone (neutral, professional, calm)
            "friction_level": 0.0,      # 0.0 to 1.0 based on corrections/cancels
        }
        try:
            self.metrics = Database.get_setting(self.metrics_key, default_metrics)
        except Exception:
            self.metrics = default_metrics
            
        # Ensure all keys exist
        for k, v in default_metrics.items():
            if k not in self.metrics:
                self.metrics[k] = v

    def save_metrics(self):
        try:
            Database.set_setting(self.metrics_key, self.metrics)
        except Exception as e:
            print(f"⚠️ [AdaptiveInteractionEngine] Failed to save metrics: {e}")

    def record_turn(self, query: str, response_length_words: int = None, cancelled: bool = False):
        """Record details of a query-response turn."""
        now = time.time()
        
        # 1. Update query length metrics
        q_words = len(query.split())
        self.metrics["query_lengths"].append(q_words)
        if len(self.metrics["query_lengths"]) > 20:
            self.metrics["query_lengths"].pop(0)

        # 2. Update response length metrics if provided
        if response_length_words:
            self.metrics["response_lengths"].append(response_length_words)
            if len(self.metrics["response_lengths"]) > 20:
                self.metrics["response_lengths"].pop(0)

        # 3. Inter-request timing
        last_t = self.metrics.get("last_request_time", 0.0)
        if last_t > 0:
            delay = now - last_t
            self.metrics["inter_request_delays"].append(delay)
            if len(self.metrics["inter_request_delays"]) > 20:
                self.metrics["inter_request_delays"].pop(0)
        self.metrics["last_request_time"] = now

        # 4. Handle cancellation/interruption
        if cancelled:
            self.metrics["interruption_count"] += 1
            # Increase friction
            self.metrics["friction_level"] = min(1.0, self.metrics["friction_level"] + 0.2)
        else:
            # Decay friction slowly with successful turns
            self.metrics["friction_level"] = max(0.0, self.metrics["friction_level"] - 0.05)

        self.save_metrics()

    def record_correction(self):
        """FrictionDetector triggered a correction."""
        self.metrics["corrections_count"] += 1
        self.metrics["friction_level"] = min(1.0, self.metrics["friction_level"] + 0.25)
        self.save_metrics()

    def determine_posture(self, user_input: str, active_app: str = None) -> str:
        """
        Determine the response posture (SILENT, SHORT_ACK, NORMAL, DETAILED, REFLECTIVE)
        based on active app, time of day, query history, and friction level.
        """
        now_dt = datetime.now()
        hour = now_dt.hour
        
        # 1. Late-night exhausted usage check (11 PM - 5 AM)
        is_late_night = (hour >= 23 or hour < 5)
        
        # 2. Rapid-fire check (delays between turns are small, e.g. < 15 seconds)
        delays = self.metrics.get("inter_request_delays", [])
        is_rapid_fire = len(delays) >= 2 and all(d < 15.0 for d in delays[-2:])
        
        # 3. Average query length check
        query_lens = self.metrics.get("query_lengths", [])
        avg_q_len = sum(query_lens) / len(query_lens) if query_lens else 5
        
        # 4. Friction level
        friction = self.metrics.get("friction_level", 0.0)

        # 5. App-based behavior check
        is_coding = active_app in ["code.exe", "devenv.exe", "pycharm64.exe", "idea64.exe"] if active_app else False
        
        # Determine Posture
        # Rule 1: High friction -> immediately scale down to SHORT_ACK to avoid annoying the user
        if friction > 0.5:
            return "SHORT_ACK"
        
        # Rule 2: Rapid fire utility commands -> SILENT (mostly silent tool outputs)
        if is_rapid_fire and (user_input.lower().startswith(("open", "close", "mute", "volume", "timer", "reminder")) or avg_q_len < 4):
            return "SILENT"

        # Rule 3: Coding mode -> SHORT_ACK (terse)
        if is_coding:
            return "SHORT_ACK"

        # Rule 4: Late-night exhausted -> calm NORMAL
        if is_late_night:
            return "NORMAL"

        # Rule 5: Brainstorming or details requested -> DETAILED
        brainstorm_keywords = ["brainstorm", "explain", "detail", "how does", "why is", "compare", "suggest"]
        if any(kw in user_input.lower() for kw in brainstorm_keywords):
            return "DETAILED"

        # Default is NORMAL
        return "NORMAL"


class FrictionDetector:
    """
    Friction Detector (Phase A)
    ===========================
    Monitors user input for phrases signaling correction, frustration, or impatience.
    """
    
    def __init__(self, engine: AdaptiveInteractionEngine):
        self.engine = engine
        self.correction_patterns = [
            r"^(no|stop|cancel|wait|wrong|not that|re-run|redo|incorrect)\b",
            r"\b(u messed up|you messed up|stupid|dumb|bad bot)\b",
            r"\b(dont do that|don't do that|stop that|no i meant)\b"
        ]

    def analyze_input(self, user_input: str) -> bool:
        text = user_input.lower().strip()
        for pattern in self.correction_patterns:
            if re.search(pattern, text):
                self.engine.record_correction()
                return True
        return False
