"""
Verification Script for V11.3 Context Valve (Ephemeral RAG)
Tests:
1. Executor interception of large outputs.
2. EphemeralManager ingestion.
3. query_ephemeral tool retrieval.
"""
import sys
import os
import asyncio
import json
from unittest.mock import MagicMock, patch

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sakura_assistant.core.executor import ToolExecutor, ExecutionResult
from sakura_assistant.core.ephemeral_manager import EphemeralManager
from sakura_assistant.core.tools_libs.memory_tools import query_ephemeral

async def test_context_valve():
    print("\n🛡️ Testing V11.3 Context Valve...")
    
    # 1. Setup Mock Ephemeral Manager
    mock_eph_man = MagicMock()
    mock_eph_man.ingest_text.return_value = "eph_test_123"
    
    # 2. Setup Mock Tool that returns large output
    mock_tool = MagicMock()
    mock_tool.name = "big_tool"
    mock_tool.invoke.return_value = "A" * 5000 
    
    # Mock ainvoke for async path
    async def mock_ainvoke(*args, **kwargs):
        return "A" * 5000
    mock_tool.ainvoke = mock_ainvoke
    
    # 3. Initialize Executor with patched Manager
    executor = ToolExecutor([mock_tool])
    
    with patch('sakura_assistant.core.executor.get_ephemeral_manager', return_value=mock_eph_man):
        # 4. Execute Plan
        step = {"tool": "big_tool", "args": {}, "id": 1}
        result = await executor.aexecute_plan([step])
        
        # 5. Verify Interception
        output = result.outputs
        print(f"   Original Output Size: 5000 chars")
        print(f"   Executor Result Length: {len(output)}")
        print(f"   Executor Output Preview: {output[:200]}")
        
        if "Context Overflow Protection" in output:
            print("✅ Interception Triggered Successfully")
        else:
            print("❌ Interception FAILED")
            return
            
        # Verify Ingest Call
        mock_eph_man.ingest_text.assert_called_once()
        print("✅ EphemeralManager.ingest_text() called")

async def test_ephemeral_query():
    print("\n📦 Testing Ephemeral Query Tool...")
    
    # Mock Manager Query
    mock_eph_man = MagicMock()
    mock_eph_man.query.return_value = "Found relevant context about AAAA..."
    
    with patch('sakura_assistant.core.ephemeral_manager.get_ephemeral_manager', return_value=mock_eph_man):
        res = query_ephemeral.invoke({"ephemeral_id": "eph_test_123", "query": "What is A?"})
        print(f"   Query Result: {res}")
        
        if "Found relevant context" in res:
             print("✅ query_ephemeral tool works")
        else:
             print("❌ query_ephemeral failed")

async def main():
    await test_context_valve()
    await test_ephemeral_query()
    print("\n🎉 V11.3 Context Valve Verification COMPLETE.")

if __name__ == "__main__":
    asyncio.run(main())
