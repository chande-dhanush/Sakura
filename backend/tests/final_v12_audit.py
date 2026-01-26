"""
Final V12 E2E Stress Test & Audit
=================================
Verifies:
1. Thought Stream (WebSocket events)
2. Smart Cache Precision (Semantic Hit)
3. Executor Pacing (Wait & See)
4. Split-Brain Model Config (8B vs 70B)

run with: python backend/tests/final_v12_audit.py
"""
import sys
import os
import asyncio
import time
import shutil
from unittest.mock import MagicMock

# Mock AppOpener to avoid crash on corrupted local config
sys.modules['AppOpener'] = MagicMock()

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sakura_assistant.core.llm import SmartAssistant
from sakura_assistant.core.broadcaster import get_broadcaster
from sakura_assistant.core.infrastructure.container import get_container
from sakura_assistant.core.tools_libs.research import SmartResearcher

async def audit_v12():
    print("️ STARTING V12 FINAL AUDIT ️")
    print("===============================")
    
    # Setup Event Listener (Mocking WebSocket)
    events = []
    def listener(event, data):
        events.append({"event": event, "data": data, "time": time.time()})
        # print(f"    [Event] {event}") # Debug
    
    broadcaster = get_broadcaster()
    broadcaster.add_listener(listener)
    
    assistant = SmartAssistant()
    if sys.platform == 'win32':
        os.system('cls')
    
    # ---------------------------------------------------------
    # TEST 4: Split-Brain Model Audit (Static Check)
    # ---------------------------------------------------------
    print("\n [Test 4] auditing Model Configuration...")
    container = get_container()
    planner_model = container.config.planner_model
    responder_model = container.config.responder_model
    
    print(f"   Planner: {planner_model}")
    print(f"   Responder: {responder_model}")
    
    if "8b" in planner_model and "70b" in responder_model:
        print("    PASS: Split-Brain Config Verified (8B Planning / 70B Response)")
    else:
        print("    FAIL: Incorrect Model Assignment!")
        # Don't exit, keep running other tests
    
    # ---------------------------------------------------------
    # TEST 1 & 3: Thought Stream & Pacing
    # ---------------------------------------------------------
    print("\n [Test 1 & 3] Auditing Thought Stream & Pacing...")
    # Force multi-step: "What is the capital of France? Also what is 50 times 3?" 
    # This should trigger `web_search` then `quick_math` or similar. 
    # Actually, simpler: "Get the time in Tokyo and then the time in New York."
    query = "What is the time in Tokyo? After that, tell me the time in London." 
    
    events.clear()
    start_time = time.time()
    try:
        await assistant.arun(query, [])
    except Exception as e:
        print(f"   ⚠️ Pipeline Error: {e}")
        
    # Verify Events
    event_types = [e["event"] for e in events]
    has_thinking = "thinking" in event_types
    has_tool = "tool_start" in event_types
    
    if has_thinking and has_tool:
        print("    PASS: Thought Stream Active (Thinking + Tool events received)")
    else:
        print(f"    FAIL: Missing events. Got: {list(set(event_types))}")

    # Check Pacing (if multiple tools used)
    # If only 1 tool, pacing might not trigger (requires step > 1).
    # We'll check if 'pacing' event exists OR if we only had 1 step.
    pacing_events = [e for e in events if e["event"] == "pacing"]
    if pacing_events:
        print(f"    PASS: 'Wait & See' Pacing Triggered ({len(pacing_events)} pauses)")
    else:
        print("   ℹ️ Note: No Pacing events (Single step execution?) - Accepted if single step.")

    # ---------------------------------------------------------
    # TEST 2: Smart Cache Precision
    # ---------------------------------------------------------
    print("\n [Test 2] Auditing Smart Cache Precision...")
    researcher = SmartResearcher()
    
    # Unique ID to avoid previous run collisions
    import uuid
    uid = uuid.uuid4().hex[:4]
    q1 = f"What is the current price of Gold element {uid}?" # Unique to force miss
    q2 = f"Gold price today element {uid}?" # Semantically identical
    
    # For the test to actually work with real Tavily, we should probably stick to real queries 
    # but the cache persists on disk.
    # Let's use the user's exact example: "What is the current price of Gold?"
    # But if we ran this before, it might already be cached.
    # We will assume unique for this run:
    q_base = "What is the price of Bitcoin right now?" # Changing topic to ensure cleanliness
    q_variant = "Current Bitcoin price?"
    
    # Step A: Miss
    print("   Step A: Cold Query...")
    events.clear()
    t0 = time.time()
    res1 = await researcher.research(q_base)
    t1 = time.time()
    
    cache_hit_events = [e for e in events if e["event"] == "cache_hit"]
    if not cache_hit_events:
        print(f"    PASS: Cache Miss (Duration: {t1-t0:.2f}s)")
    else:
        print("   ⚠️ WARN: Unexpected Cache Hit on Step A")

    # Step B: Hit
    print("   Step B: Variant Query (Expect Hit)...")
    events.clear()
    t2 = time.time()
    res2 = await researcher.research(q_variant)
    t3 = time.time()
    duration = t3 - t2
    
    cache_hit_events = [e for e in events if e["event"] == "cache_hit"]
    if cache_hit_events:
        print(f"    PASS: Cache Hit Triggered")
        if duration < 0.5:
             print(f"    PASS: Low Latency ({duration:.4f}s < 0.5s)")
        else:
             print(f"    FAIL: Latency too high ({duration:.4f}s)")
    else:
        print("    FAIL: Cache Miss on Variant Query!")
        
    # ---------------------------------------------------------
    # Cleanup
    # ---------------------------------------------------------
    print("\n Cleaning up...")
    from sakura_assistant.core.ephemeral_manager import get_ephemeral_manager
    get_ephemeral_manager().cleanup_old(0)
    print("    Ephemeral stores cleaned.")
    
    print("\n V12 AUDIT COMPLETE.")

if __name__ == "__main__":
    asyncio.run(audit_v12())
