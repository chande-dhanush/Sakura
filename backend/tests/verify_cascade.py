from sakura_assistant.core.planner import Planner
from sakura_assistant.core.micro_toolsets import get_micro_toolset, detect_semantic_intent

class MockLLM:
    def bind_tools(self, tools): return self
    async def ainvoke(self, messages): return None

def test_cascade():
    print("🧪 Starting Search Cascade Test...")
    p = Planner(MockLLM())
    
    # Mock tools
    class Tool:
        def __init__(self, name): self.name = name
    all_tools = [Tool(n) for n in ['web_search', 'search_wikipedia', 'get_system_info']]
    
    # 1. Normal Gating (No history)
    print("Test 1: Normal Gating")
    try:
        tools = p._filter_tools(all_tools, "search", "Who is Elon Musk?", hindsight=None, tool_history=None)
        names = [t.name for t in tools]
        print(f"Tools: {names}") 
        if "web_search" not in names and "search_wikipedia" in names:
            print("✅ Tavily HIDDEN")
        else:
            print("❌ Gating Failed")
    except Exception as e:
        print(f"❌ Test 1 Error: {e}")

    # 2. Cascade (With history)
    print("\nTest 2: Cascade Trigger (History present)")
    history = [{"tool": "search_wikipedia", "result": "No results"}]
    try:
        tools = p._filter_tools(all_tools, "search", "Who is Elon Musk?", hindsight=None, tool_history=history)
        names = [t.name for t in tools]
        print(f"Tools: {names}")
        if "web_search" in names:
            print("✅ Tavily UNLOCKED (Cascade worked)")
        else:
            print("❌ Cascade Failed - Tavily still hidden")
    except Exception as e:
        print(f"❌ Test 2 Error: {e}")

if __name__ == "__main__":
    test_cascade()
