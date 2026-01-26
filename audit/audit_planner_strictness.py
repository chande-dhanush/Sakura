import sys
import os
import asyncio
from langchain_core.messages import HumanMessage

# Add project root to path
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

# Mock LLM for speed, or use real one? Real one is needed to test prompts.
from sakura_assistant.core.infrastructure.container import get_container, reset_container
from sakura_assistant.core.execution.planner import Planner

def test_planner_strictness():
    """Verify Planner follows the 'Force Tool' and 'Think Fast' rules."""
    
    # 1. Setup
    print("🧠 Initializing Planner Audit...")
    reset_container()
    container = get_container()
    llm = container.get_planner_llm()
    planner = Planner(llm)
    
    # 2. Test Cases
    test_cases = [
        {
            "query": "Look up the brand that starts with Victoria",
            "expected_tool": "web_search",
            "fail_reason": "Memory Recall (Lazy Planner)"
        },
        {
            "query": "What is the price of Bitcoin right now?",
            "expected_tool": "web_search",
            "fail_reason": "Hallucination (Dynamic Fact)"
        },
        {
            "query": "Play some jazz",
            "expected_tool": "spotify_control",
            "fail_reason": "Wrong Tool"
        }
    ]
    
    print(f"\n🧪 Testing {len(test_cases)} scenarios...\n")
    
    results = []
    
    for case in test_cases:
        query = case["query"]
        print(f"   Query: '{query}'")
        
        # Run Async Plan
        # We need a loop for async
        try:
            plan_result = asyncio.run(planner.aplan(query, intent_mode="action"))
            plan = plan_result.get("plan", [])
            
            tool_names = [step["tool"] for step in plan]
            
            # Check correctness
            expected = case["expected_tool"]
            success = any(t == expected for t in tool_names)
            
            if success:
                print(f"   ✅ PASS: Used {tool_names}")
                results.append(True)
            else:
                print(f"   ❌ FAIL: Used {tool_names} (Expected: {expected})")
                print(f"      Reason: {case['fail_reason']}")
                results.append(False)
                
        except Exception as e:
            print(f"   ⚠️ ERROR: {e}")
            results.append(False)
            
        print("-" * 40)

    # 3. Summary
    score = sum(results) / len(results) * 100
    print(f"\n📊 Strictness Score: {score:.1f}% ({sum(results)}/{len(results)})")
    
    if score == 100:
        print("🏆 Planner is STRICT and OBEDIENT.")
    else:
        print("👮 Planner needs more discipline.")

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    test_planner_strictness()
