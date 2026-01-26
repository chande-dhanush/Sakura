import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_oneshot():
    print("Testing ONE_SHOT path for 'play shape of you'...")
    from backend.sakura_assistant.core.llm import SmartAssistant
    assistant = SmartAssistant()
    
    # We want to see if Dispatcher picks ONE_SHOT
    # We'll mock the router result or just let it run
    print("Query: play shape of you")
    response_stream = assistant.router.route("play shape of you")
    route = await assistant.router.aroute("play shape of you")
    print(f"Router Result: {route.classification} | tool={route.tool_hint}")
    
    # Check Dispatcher logic
    mode = assistant.dispatcher._determine_mode(route.classification, route.tool_hint, "play shape of you")
    print(f"Dispatcher Mode: {mode}")
    
    if mode.value == "ONE_SHOT":
        print("✅ ONE_SHOT path verified for direct query")
    else:
        print("❌ ONE_SHOT path NOT taken")

if __name__ == "__main__":
    asyncio.run(test_oneshot())
