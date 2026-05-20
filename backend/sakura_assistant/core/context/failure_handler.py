from typing import Dict, Any, List
from ..database import Database

class TrustAwareFailureHandler:
    """
    Trust-Aware Failure Handler (Step 6)
    ====================================
    Calibrates trust level based on failures and corrections, modifying response behavior.
    """
    
    def __init__(self):
        self.trust_key = "trust_metrics"
        self._load_trust_metrics()

    def _load_trust_metrics(self):
        default_metrics = {
            "trust_score": 1.0,           # 0.0 to 1.5
            "consecutive_failures": 0,
            "correction_count": 0,
        }
        try:
            self.metrics = Database.get_setting(self.trust_key, default_metrics)
        except Exception:
            self.metrics = default_metrics
            
        for k, v in default_metrics.items():
            if k not in self.metrics:
                self.metrics[k] = v

    def save_metrics(self):
        try:
            Database.set_setting(self.trust_key, self.metrics)
        except Exception as e:
            print(f"⚠️ [TrustAwareFailureHandler] Failed to save trust metrics: {e}")

    def record_success(self):
        self.metrics["consecutive_failures"] = 0
        self.metrics["trust_score"] = min(1.5, self.metrics["trust_score"] + 0.05)
        self.save_metrics()

    def record_failure(self):
        self.metrics["consecutive_failures"] += 1
        penalty = 0.1 * self.metrics["consecutive_failures"]
        self.metrics["trust_score"] = max(0.0, self.metrics["trust_score"] - penalty)
        self.save_metrics()

    def record_correction(self):
        self.metrics["correction_count"] += 1
        self.metrics["trust_score"] = max(0.0, self.metrics["trust_score"] - 0.15)
        self.save_metrics()

    def get_trust_level(self) -> float:
        return self.metrics.get("trust_score", 1.0)

    def handle_tool_failure(self, tool_name: str, error_msg: str, partial_success: str = None) -> Dict[str, Any]:
        """Synthesizes a structured response posture directive and message based on trust."""
        self.record_failure()
        trust = self.get_trust_level()
        
        if trust < 0.6:
            phrasing = "humble_transparent"
            suggest_manual = True
        else:
            phrasing = "calm_direct"
            suggest_manual = False

        explanation = f"I ran into an issue running '{tool_name}': {error_msg}."
        if partial_success:
            explanation = f"I succeeded in {partial_success}, but couldn't finish '{tool_name}': {error_msg}."
            
        return {
            "success": False,
            "phrasing": phrasing,
            "explanation": explanation,
            "suggest_manual": suggest_manual,
            "trust_score": trust
        }
