import asyncio
import os
import sys
import json

# Setup paths
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

from sakura_assistant.core.llm import SmartAssistant
from sakura_assistant.memory.faiss_store import get_memory_store

async def test_memory_flow():
    print("  [Test] Initializing SmartAssistant...")
    assistant = SmartAssistant()
    store = get_memory_store()
    
    # 1. Ensure clear start
    print("  [Test] Clearing all memory...")
    # Simulate the /clear endpoint logic
    assistant.world_graph.reset()
    assistant.world_graph.save()
    assistant.summary_memory.clear()
    store.clear_all_memory()
    
    # 2. Test Memory Write (CHAT route)
    print("\n  [Test] Step 1: Writing memory (CHAT route)...")
    user_input = "my favourite song is no friends by cadmium"
    print(f"User: {user_input}")
    
    # Run the assistant (this should trigger MemoryJudger async)
    result = await assistant.arun(user_input, history=[])
    print(f"Sakura: {result['content']}")
    
    # Wait for the async MemoryJudger task to complete
    print("  [Test] Waiting for MemoryJudger (async task)...")
    await asyncio.sleep(20) # Allow time for LLM call and storage
    
    # 3. Verify FAISS storage (Budget: 2500 chars)
    print("\n  [Test] Step 2: Verifying FAISS storage...")
    memories_text = store.get_context_for_query("favourite song")
    print(f"Retrieved context:\n{memories_text}")
    
    found = "no friends" in memories_text.lower() and "cadmium" in memories_text.lower()
    if found:
        print("  [Test] SUCCESS: Fact stored in FAISS.")
    else:
        print("  [Test] FAILURE: Fact not found in FAISS.")
    
    # 4. Test Memory Recall
    print("\n  [Test] Step 3: Testing Memory Recall...")
    recall_query = "do you remember my favourite song?"
    print(f"User: {recall_query}")
    recall_result = await assistant.arun(recall_query, history=[])
    response_text = recall_result.get('content', '')
    print(f"Sakura: {response_text}")
    
    if "no friends" in response_text.lower():
        print("  [Test] SUCCESS: Sakura recalled the song.")
    else:
        print("  [Test] FAILURE: Sakura did not recall the song.")
        
    # 5. Test Clear Reset
    print("\n  [Test] Step 4: Testing Clear Reset...")
    # Simulate /clear
    store.clear_all_memory()
    print("FAISS cleared.")
    
    # Verify it's gone
    print("  [Test] Verifying memory is gone...")
    # Clear cache since it's an LRU
    store.get_context_for_query.cache_clear()
    post_clear_text = store.get_context_for_query("favourite song")
    print(f"Retrieved context (post-clear):\n{post_clear_text}")
    
    if "no friends" not in post_clear_text.lower():
        print("  [Test] SUCCESS: Memory wiped.")
    else:
        print("  [Test] FAILURE: Memory still exists after clear.")

if __name__ == "__main__":
    asyncio.run(test_memory_flow())
