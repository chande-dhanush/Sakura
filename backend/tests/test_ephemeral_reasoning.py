"""
FIX-12 Tests: Ephemeral data_reasoning Flag
===========================================
Verifies that the presence of an Ephemeral Store ID correctly
triggers the data_reasoning flag in the ResponseContext.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock
import asyncio
import sys

# Mock modules that spawn background threads on import to prevent pytest hangs
sys.modules['pygame'] = MagicMock()
sys.modules['sakura_assistant.utils.stability_logger'] = MagicMock()

try:
    from sakura_assistant.core.llm import SmartAssistant
except Exception:
    pass # In case mocking broke something, but we just need the class structure
from sakura_assistant.core.llm import SmartAssistant
from sakura_assistant.core.models.responder import ResponseContext
from sakura_assistant.core.execution.context import ExecutionResult, ExecutionStatus

class TestEphemeralReasoningFlag:
    def _make_mock_assistant(self, tool_output):
        # We need to test the arun() inner logic without triggering real models
        assistant = object.__new__(SmartAssistant)
        
        # Mock dependencies accessed in arun()
        assistant.router = AsyncMock()
        assistant.router.aroute.return_value = MagicMock(needs_tools=True, classification="PLAN", tool_hint=None)
        
        assistant.executor_layer = AsyncMock()
        exec_res = ExecutionResult(
            outputs=tool_output,
            tool_messages=[],
            tool_used="dummy",
            last_result={},
            status=ExecutionStatus.SUCCESS
        )
        assistant.executor_layer.dispatch.return_value = exec_res
        
        assistant.world_graph = MagicMock()
        assistant.summary_memory = MagicMock()
        
        assistant.context_manager = MagicMock()
        assistant.context_manager.get_context_for_llm.return_value = {
            "responder_context": "",
            "intent_adjustment": "",
            "current_mood": "Neutral",
            "summary_context": ""
        }
        
        assistant.desire_system = MagicMock()
        assistant.desire_system.get_mood_prompt.return_value = ""
        
        # We want to capture the constructed ResponseContext
        assistant.responder = AsyncMock()
        
        async def mock_agenerate(resp_context):
            assistant.captured_context = resp_context
            return "Done"
            
        assistant.responder.agenerate = AsyncMock(side_effect=mock_agenerate)
        assistant._last_turn_data = {}
        
        return assistant

    def test_flag_true_on_ephemeral_string(self):
        """1. When tool_outputs contains 'Ephemeral Store ID: eph_abc' 
        -> data_reasoning=True is passed to ResponseContext."""
        output = "Output too large. Saved to Ephemeral Store ID: eph_abc123."
        assistant = self._make_mock_assistant(output)
        
        dummy_state = MagicMock()
        dummy_state.current_intent = ""
        
        asyncio.run(assistant.arun("analyze this giant file", dummy_state))
        
        ctx = assistant.captured_context
        assert ctx.data_reasoning is True, "Expected data_reasoning to be True for ephemeral output"

    def test_flag_false_on_normal_string(self):
        """2. When tool_outputs contains normal text -> data_reasoning=False."""
        output = "The weather is 24 degrees."
        assistant = self._make_mock_assistant(output)
        
        dummy_state = MagicMock()
        
        asyncio.run(assistant.arun("what is the weather", dummy_state))
        
        ctx = assistant.captured_context
        assert ctx.data_reasoning is False, "Expected data_reasoning to be False for normal text"

    def test_flag_false_on_none(self):
        """3. When tool_outputs is None -> data_reasoning=False (no crash)."""
        output = None 
        assistant = self._make_mock_assistant(output)
        
        dummy_state = MagicMock()
        
        asyncio.run(assistant.arun("broken tool", dummy_state))
        
        ctx = assistant.captured_context
        assert ctx.data_reasoning is False, "Expected data_reasoning to be False for None output"
