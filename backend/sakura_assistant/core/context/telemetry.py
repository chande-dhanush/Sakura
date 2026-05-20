import time
from typing import Dict, Any, List
from ..database import Database

class ReliabilityTelemetry:
    """
    Reliability Telemetry Engine (Step 7)
    ====================================
    Tracks tool success rates, cancellation rates, planner turns, and latency
    in SQLite settings for long-term health reporting.
    """
    
    def __init__(self):
        self.telemetry_key = "reliability_telemetry"
        self._load_telemetry()

    def _load_telemetry(self):
        default_stats = {
            "total_runs": 0,
            "failed_runs": 0,
            "cancelled_runs": 0,
            "tool_executions": {}, # dict mapping tool_name to {"success": int, "failure": int}
            "planner_runs": 0,
            "planner_successes": 0,
            "context_mismatch_events": 0,
            "latency_history": []   # list of float seconds
        }
        try:
            self.stats = Database.get_setting(self.telemetry_key, default_stats)
        except Exception:
            self.stats = default_stats
            
        for k, v in default_stats.items():
            if k not in self.stats:
                self.stats[k] = v

    def save_telemetry(self):
        try:
            Database.set_setting(self.telemetry_key, self.stats)
        except Exception as e:
            print(f"⚠️ [ReliabilityTelemetry] Failed to save telemetry: {e}")

    def record_run(self, success: bool, cancelled: bool = False, latency: float = 0.0, is_planner: bool = False):
        self.stats["total_runs"] += 1
        if cancelled:
            self.stats["cancelled_runs"] += 1
        elif not success:
            self.stats["failed_runs"] += 1
            
        if is_planner:
            self.stats["planner_runs"] += 1
            if success and not cancelled:
                self.stats["planner_successes"] += 1
                
        if latency > 0:
            self.stats["latency_history"].append(latency)
            if len(self.stats["latency_history"]) > 50:
                self.stats["latency_history"].pop(0)
                
        self.save_telemetry()

    def record_tool_execution(self, tool_name: str, success: bool):
        if tool_name not in self.stats["tool_executions"]:
            self.stats["tool_executions"][tool_name] = {"success": 0, "failure": 0}
            
        if success:
            self.stats["tool_executions"][tool_name]["success"] += 1
        else:
            self.stats["tool_executions"][tool_name]["failure"] += 1
            
        self.save_telemetry()

    def record_context_mismatch(self):
        self.stats["context_mismatch_events"] += 1
        self.save_telemetry()

    def get_report(self) -> Dict[str, Any]:
        total = self.stats["total_runs"]
        fail = self.stats["failed_runs"]
        cancel = self.stats["cancelled_runs"]
        
        success_rate = (total - fail - cancel) / total if total > 0 else 1.0
        
        tool_stats = {}
        for tool, counts in self.stats["tool_executions"].items():
            t_total = counts["success"] + counts["failure"]
            tool_stats[tool] = {
                "total": t_total,
                "success_rate": counts["success"] / t_total if t_total > 0 else 1.0
            }
            
        return {
            "total_runs": total,
            "success_rate": success_rate,
            "cancellation_rate": cancel / total if total > 0 else 0.0,
            "failure_rate": fail / total if total > 0 else 0.0,
            "tool_reliability": tool_stats,
            "planner_runs": self.stats["planner_runs"],
            "planner_success_rate": self.stats["planner_successes"] / self.stats["planner_runs"] if self.stats["planner_runs"] > 0 else 1.0,
            "context_mismatch_events": self.stats["context_mismatch_events"]
        }
