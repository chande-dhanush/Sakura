import asyncio
import random
import json
import os
from typing import List, Dict, Any
from .failure_tracker import FailureTracker
from .chaos_manager import ChaosManager

class SessionEngine:
    def __init__(self, assistant: Any, tracker: FailureTracker, chaos: ChaosManager):
        self.assistant = assistant
        self.tracker = tracker
        self.chaos = chaos
        
        # Load Scenarios
        scenario_path = os.path.join(os.path.dirname(__file__), "scenarios.json")
        with open(scenario_path, "r", encoding="utf-8") as f:
            self.scenarios = json.load(f)

    async def run_session(self, session_id: str, num_turns: int = 20, tier: str = "medium"):
        print(f"\n>>> STARTING SESSION: {session_id} (Tier: {tier})")
        self.tracker.start_session(session_id)
        history = []
        
        # Filter scenarios by tier
        tier_scenarios = [s for s in self.scenarios if s["tier"] == tier]
        if not tier_scenarios:
            tier_scenarios = self.scenarios # Fallback
            
        for i in range(num_turns):
            # Pick a scenario
            scenario = random.choice(tier_scenarios)
            query = scenario["query"]

            print(f"   [TURN {i+1}] [{tier.upper()}] User: {query}")
            
            try:
                # arun(user_input, history, image_data=None, llm_overrides=None)
                response = await self.assistant.arun(query, history)
                
                # Consume any chaos injected during this turn
                chaos_events = self.chaos.consume_chaos()
                
                self.tracker.record_turn(session_id, i, query, response, chaos_events, scenario=scenario)
                
                # Update history
                history.append({"role": "user", "content": query})
                history.append({"role": "assistant", "content": response.get("content", "")})
                
                # Trim history if it gets too long
                if len(history) > 40:
                    history = history[-40:]
                    
            except Exception as e:
                print(f"   [ERROR] Turn {i+1} failed: {e}")
                self.tracker.record_turn(session_id, i, query, {"content": str(e), "metadata": {"status": "error", "error": str(e)}}, [], scenario=scenario)
                break

    async def run_audit_suite(self, num_sessions: int = 30, turns_per_session: int = 20):
        # Distributed sessions across tiers
        tiers = ["easy"] * (num_sessions // 3) + ["medium"] * (num_sessions // 3) + ["chaotic"] * (num_sessions - 2 * (num_sessions // 3))
        
        for i, tier in enumerate(tiers):
            session_id = f"session_{i+1}_{tier}_{int(asyncio.get_event_loop().time())}"
            await self.run_session(session_id, turns_per_session, tier=tier)
        
        print("\n>>> AUDIT SUITE COMPLETE")
