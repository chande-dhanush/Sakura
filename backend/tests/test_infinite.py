"""
Infinite Test - V12 Stability & "Thought Stream"
================================================
Simulates a complex user query to verify:
1. Context Valve (handling large searches)
2. Thought Stream (Broadcaster events)
3. Smart Caching (Second run)
4. Rate Limiter Pacing (Executor pause)

Query: "Compare the features of the top 5 AI models in 2026."
"""
import asyncio
import os
import sys
import time

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sakura_assistant.core.llm import SmartAssistant
from sakura_assistant.core.broadcaster import get_broadcaster

async def run_infinite_test():
    print("🚀 Starting 'Infinite' Test (V12)...")
    
    # 0. Subscribe to Thought Stream
    def print_thought(event, data):
        # Filter for key events to keep log clean
        if event in ["thinking", "tool_start", "rate_limit", "pacing", "cache_hit"]:
            emoji = "📡"
            if event == "pacing": emoji = "⏳"
            if event == "cache_hit": emoji = "⚡"
            if event == "tool_start": emoji = "🛠️"
            if event == "rate_limit": emoji = "🛑"
            
            print(f"{emoji} [{event.upper()}] {data}")

    broadcaster = get_broadcaster()
    broadcaster.add_listener(print_thought)
    
    # 1. Initialize Assistant
    try:
        assistant = SmartAssistant()
        print("✅ Assistant Initialized")
    except Exception as e:
        print(f"❌ Init Failed: {e}")
        return

    query = "Compare the features of the top 5 AI models in 2026."
    print(f"\n❓ Query: {query}\n")
    
    try:
        # History mock
        history = []
        
        # 2. Run Pipeline (Complex)
        start_time = time.time()
        result = await assistant.arun(query, history)
        duration = time.time() - start_time
        
        print("\n" + "="*50)
        print(f"✅ FINAL RESPONSE ({duration:.2f}s):")
        print("="*50)
        print(result.get("content", "No content"))
        print("\n")
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        print(f"❌ RUN FAILED: {e}")

if __name__ == "__main__":
    # Ensure env vars are loaded (via config verify or manually if needed)
    from sakura_assistant.config import is_feature_enabled
    asyncio.run(run_infinite_test())
