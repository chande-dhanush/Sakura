import json
import os
import time
from typing import Dict, Any, List, Optional
from datetime import datetime

class FailureTracker:
    def __init__(self, vault_path: str = "audit/data/adversarial_vault"):
        self.vault_path = vault_path
        os.makedirs(self.vault_path, exist_ok=True)
        self.session_data = {}
        self.current_session_id = None

    def start_session(self, session_id: str):
        self.current_session_id = session_id
        self.session_data[session_id] = {
            "start_time": datetime.now().isoformat(),
            "turns": [],
            "metrics": {}
        }

    def record_turn(self, session_id: str, turn_index: int, query: str, response: Dict[str, Any], chaos_applied: List[Dict[str, Any]], scenario: Optional[Dict] = None):
        metadata = response.get("metadata", {})
        content = response.get("content", "").lower()
        
        # Determine success (structural)
        success = metadata.get("status") == "success"
        
        # Intent Satisfaction / Task Completion (Behavioral)
        task_completed = False
        intent_satisfaction = 0.0
        evaluation_reason = ""

        if scenario:
            expected = scenario.get("expected_behavior")
            ground_truth = scenario.get("ground_truth", [])
            
            # Check for ground truth presence
            truth_matches = sum(1 for word in ground_truth if word.lower() in content)
            match_ratio = truth_matches / len(ground_truth) if ground_truth else 1.0
            
            if expected == "tool_result_required":
                if success and match_ratio > 0.5:
                    task_completed = True
                    intent_satisfaction = match_ratio
                elif any(c["type"] == "partial_corruption" for c in chaos_applied):
                    # Hallucination check for corrupted data
                    evaluation_reason = "System accepted corrupted tool data as truth"
            
            elif expected == "abstain_required":
                # Success for abstain means IT DIDN'T hallucinate a fake answer
                if any(word.lower() in content for word in ground_truth):
                    task_completed = True
                    intent_satisfaction = 1.0
                else:
                    evaluation_reason = "System failed to abstain on unanswerable query"

            elif expected == "clarify_required":
                if any(word.lower() in content for word in ground_truth):
                    task_completed = True
                    intent_satisfaction = 1.0
                else:
                    evaluation_reason = "System failed to clarify ambiguous query"

        # Hallucination detection (Refined)
        is_hallucination = False
        if scenario and scenario.get("type") == "unanswerable":
            if not task_completed and success:
                is_hallucination = True
                evaluation_reason = "Hallucinated answer for unanswerable query"
        
        if any(c["type"] == "partial_corruption" for c in chaos_applied) and success:
            # If it was corrupted but the system didn't flag it and gave a confident answer
            is_hallucination = True
            evaluation_reason = "Failed to detect data corruption"

        # Loop detection (from metadata)
        is_loop = "loop detected" in str(metadata.get("error", "")).lower() or "Catastrophic loop" in response.get("content", "")
        
        # Tool misuse
        tool_misuse = False
        tool_used = response.get("tool_used", "None")
        if tool_used == "web_search" and len(query.split()) < 2:
            tool_misuse = True

        # Recovery metrics
        recovery_attempted = len(chaos_applied) > 0
        recovery_success = success if recovery_attempted else None
        early_termination = not success and ("budget" in str(metadata.get("error")).lower() or "limit" in str(metadata.get("error")).lower())

        turn_info = {
            "turn": turn_index,
            "query": query,
            "tier": scenario.get("tier") if scenario else "unknown",
            "content": response.get("content"),
            "mode": response.get("mode"),
            "tool_used": tool_used,
            "latency": metadata.get("latency"),
            "success": success,
            "task_completed": task_completed,
            "intent_satisfaction": intent_satisfaction,
            "is_hallucination": is_hallucination,
            "is_loop": is_loop,
            "tool_misuse": tool_misuse,
            "recovery_attempted": recovery_attempted,
            "recovery_success": recovery_success,
            "early_termination": early_termination,
            "chaos_applied": chaos_applied,
            "evaluation_reason": evaluation_reason,
            "error": metadata.get("error")
        }
        
        self.session_data[session_id]["turns"].append(turn_info)
        self._save_session(session_id)

    def _save_session(self, session_id: str):
        file_path = os.path.join(self.vault_path, f"{session_id}.json")
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.session_data[session_id], f, indent=2)

    def compute_metrics(self) -> Dict[str, Any]:
        all_turns = []
        for sid in self.session_data:
            all_turns.extend(self.session_data[sid]["turns"])
        
        if not all_turns:
            return {}

        total = len(all_turns)
        structural_successes = sum(1 for t in all_turns if t["success"])
        task_completions = sum(1 for t in all_turns if t["task_completed"])
        hallucinations = sum(1 for t in all_turns if t["is_hallucination"])
        misuse = sum(1 for t in all_turns if t["tool_misuse"])
        loops = sum(1 for t in all_turns if t["is_loop"])
        
        recoveries_attempted = sum(1 for t in all_turns if t["recovery_attempted"])
        recoveries_succeeded = sum(1 for t in all_turns if t["recovery_success"] is True)
        early_terminations = sum(1 for t in all_turns if t["early_termination"])

        tier_metrics = {}
        for tier in ["easy", "medium", "chaotic"]:
            tier_turns = [t for t in all_turns if t["tier"] == tier]
            if tier_turns:
                tier_metrics[tier] = {
                    "count": len(tier_turns),
                    "success_rate": sum(1 for t in tier_turns if t["task_completed"]) / len(tier_turns)
                }

        metrics = {
            "total_turns": total,
            "structural_success_rate": structural_successes / total,
            "task_completion_rate": task_completions / total,
            "hallucination_rate": hallucinations / total,
            "tool_misuse_rate": misuse / total,
            "planner_loop_rate": loops / total,
            "recovery_success_rate": recoveries_succeeded / recoveries_attempted if recoveries_attempted > 0 else 0,
            "early_termination_rate": early_terminations / total,
            "tier_metrics": tier_metrics
        }
        
        # New Scoring Formula: Focus on behavioral success and heavy penalties for hallucinations
        # score = task_completion_rate - 0.2 * early_termination - 0.5 * loop_rate - 1.5 * hallucination_rate
        metrics["score"] = (
            metrics["task_completion_rate"] 
            - 0.2 * metrics["early_termination_rate"]
            - 0.5 * metrics["planner_loop_rate"] 
            - 1.5 * metrics["hallucination_rate"]
        )
        
        return metrics
