"""
Verification Script for V11 Features (Agentic Web & Reflection)
"""
import sys
import os
import asyncio
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sakura_assistant.core.tools_libs.research import SmartResearcher
from sakura_assistant.core.memory.reflection import ReflectionEngine

async def test_smart_researcher_logic():
    print("\n🧪 Testing SmartResearcher Logic...")
    researcher = SmartResearcher()
    
    # Test Tier Logic
    tier1_query = "Who is the CEO of Apple?"
    tier = researcher._determine_tier(tier1_query)
    print(f"   Query: '{tier1_query}' -> Tier: {tier} (Expected: basic)")
    assert tier == "basic"
    
    tier2_query = "Compare potential impact of Rust vs C++ for AI systems performance"
    tier = researcher._determine_tier(tier2_query)
    print(f"   Query: '{tier2_query}' -> Tier: {tier} (Expected: advanced)")
    assert tier == "advanced"
    
    print("✅ SmartResearcher Tier Logic Passed")

async def test_reflection_logic():
    print("\n🧪 Testing ReflectionEngine Logic...")
    
    # Mock WorldGraph to prevent real writes
    mock_wg = MagicMock()
    mock_wg.get_or_create_entity.return_value = MagicMock(id="pref:test")
    
    # Patch singleton
    ReflectionEngine._instance = None # Reset singleton
    with patch('sakura_assistant.core.memory.reflection.get_world_graph', return_value=mock_wg):
        engine = ReflectionEngine()
        engine.wg = mock_wg
        
        # Test History
        history = [
            {"role": "user", "content": "Hi there"},
            {"role": "assistant", "content": "Hello!"},
            {"role": "user", "content": "I'm learning Rust right now, it's hard."},
            {"role": "assistant", "content": "Rust is great!"}
        ]
        
        # Mock LLM to avoid API call
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = '{"entities": [{"id": "pref:lang", "summary": "Learning Rust", "attributes": {"language": "Rust"}}]}'
        
        async def mock_ainvoke(*args, **kwargs):
            return mock_response
            
        mock_llm.ainvoke = mock_ainvoke
        engine._llm = mock_llm
        
        # Run Delta Analysis
        await engine._analyze_delta(history)
        
        # Verify World Graph Update called
        print(f"   Last Reflected Index: {engine.last_reflected_index} (Expected: 4)")
        assert engine.last_reflected_index == 4
        
        mock_wg.get_or_create_entity.assert_called()
        print("✅ ReflectionEngine Graph Update Triggered")

async def main():
    await test_smart_researcher_logic()
    await test_reflection_logic()
    print("\n🎉 All V11 Logic Tests Passed!")

if __name__ == "__main__":
    asyncio.run(main())
