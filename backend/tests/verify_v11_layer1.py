"""
Verification Script for V11 Layer 1: Intelligence & Agency
1. Smart Research (Tier 2 Logic)
2. Reflection Engine (Graph Update)
"""
import sys
import os
import asyncio
import json
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sakura_assistant.core.tools_libs.research import SmartResearcher
from sakura_assistant.core.memory.reflection import ReflectionEngine

async def test_smart_research():
    print("\n🕵️ Testing V11.1 Smart Researcher...")
    researcher = SmartResearcher()
    
    # Tier 1 Case
    q1 = "Who is the CEO of Tesla?"
    t1 = researcher._determine_tier(q1)
    print(f"   [Tier 1 Check] '{q1}' -> {t1} (Expected: basic)")
    assert t1 == "basic"
    
    # Tier 2 Case
    q2 = "Compare the performance of Rust vs C++ in 2024"
    t2 = researcher._determine_tier(q2)
    print(f"   [Tier 2 Check] '{q2}' -> {t2} (Expected: advanced)")
    assert t2 == "advanced"
    
    print("✅ Smart Research Logic: PASS")

async def test_reflection_engine():
    print("\n🧠 Testing V11.2 Reflection Engine...")
    
    # 1. Mock World Graph
    mock_wg = MagicMock()
    mock_wg.get_or_create_entity.return_value = MagicMock(id="pref:food")
    
    # 2. Mock Singleton to use our mock WG
    ReflectionEngine._instance = None
    with patch('sakura_assistant.core.memory.reflection.get_world_graph', return_value=mock_wg):
        engine = ReflectionEngine()
        engine.wg = mock_wg
        
        # 3. Simulate Chat History
        history = [
            {"role": "user", "content": "Hi"},
            {"role": "assistant", "content": "Hello!"},
            # Delta starts here
            {"role": "user", "content": "I love spicy food, especially ramen."},
            {"role": "assistant", "content": "Noted! Spicy ramen is great."}
        ]
        engine.last_reflected_index = 2 # Pretend we saw the first 2 messages already
        
        # 4. Mock LLM Response
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "entities": [
                {
                    "id": "pref:food",
                    "summary": "Loves spicy food",
                    "type": "preference",
                    "attributes": {"dish": "ramen", "spice_level": "high"}
                }
            ]
        })
        
        async def mock_ainvoke(*args, **kwargs):
            return mock_response
            
        mock_llm.ainvoke = mock_ainvoke
        engine._llm = mock_llm
        
        # 5. Run Reflection
        await engine._analyze_delta(history)
        
        # 6. Verify
        print(f"   Last Reflected Index: {engine.last_reflected_index} (Expected: 4)")
        assert engine.last_reflected_index == 4
        
        # Verify call to WorldGraph
        mock_wg.get_or_create_entity.assert_called()
        args, kwargs = mock_wg.get_or_create_entity.call_args
        print(f"   Graph Update Triggered: {kwargs.get('name')} (Attributes: {kwargs.get('attributes')})")
        
        print("✅ Reflection Engine Logic: PASS")

async def main():
    await test_smart_research()
    await test_reflection_engine()
    print("\n🎉 V11 Layer 1 Verification COMPLETE.")

if __name__ == "__main__":
    asyncio.run(main())
