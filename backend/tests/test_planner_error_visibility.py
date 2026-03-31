"""
FIX-09 Tests: Planner Error Visibility
=======================================
Verifies that when the Planner fails (e.g., API timeout), the
ReActLoop bubbles the error up via ExecutionResult instead of
silently swallowing it and returning a generic completion.
"""
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock
from sakura_assistant.core.execution.executor import ReActLoop
from sakura_assistant.core.execution.context import ExecutionResult, ExecutionStatus


class DummyPlanner:
    def __init__(self, responses):
        self._call_count = 0
        self.responses = responses
        
    async def aplan(self, **kwargs):
        idx = min(self._call_count, len(self.responses) - 1)
        self._call_count += 1
        return self.responses[idx]

    def plan(self, **kwargs):
        idx = min(self._call_count, len(self.responses) - 1)
        self._call_count += 1
        return self.responses[idx]


def _make_loop(planner_responses):
    planner = DummyPlanner(planner_responses)
    # Mocking minimum dependencies for ReActLoop
    loop = ReActLoop(
        planner=planner,
        tool_runner=MagicMock(),
        output_handler=MagicMock(),
        policy=MagicMock()
    )
    
    # Mock execution to return a dummy successful ExecResult
    exec_res = ExecutionResult(
        outputs="Tool output", 
        tool_messages=[MagicMock()], 
        tool_used="test_tool",
        last_result={},
        status=ExecutionStatus.SUCCESS
    )
    loop._aexecute_steps = AsyncMock(return_value=exec_res)
    loop._execute_steps = MagicMock(return_value=exec_res)
    return loop


class TestPlannerErrorVisibility:
    
    def test_planner_error_bubbles_up(self):
        """1. When planner returns an error, ReActLoop returns ExecutionResult.error."""
        loop = _make_loop([
            {"steps": [], "complete": False, "error": "Groq API Timeout"}
        ])
        
        result = asyncio.run(loop.arun(user_input="test query"))
        
        assert result.status == ExecutionStatus.FAILED, "Result should map to error status"
        assert "Groq API Timeout" in result.outputs

    def test_normal_completion_unchanged(self):
        """2. When planner normally completes without steps, loop exits cleanly."""
        loop = _make_loop([
            {"steps": [], "complete": True}
        ])
        
        result = asyncio.run(loop.arun(user_input="test query"))
        
        # It shouldn't be an error.
        assert result.status != ExecutionStatus.FAILED

    def test_steps_then_completion(self):
        """3. Loop completes normally after executing steps followed by an empty plan."""
        loop = _make_loop([
            # First iteration: a step to run
            {"steps": [{"id": 1, "tool": "test_tool", "args": {}}], "complete": False},
            # Second iteration: no steps, done
            {"steps": [], "complete": True}
        ])
        
        result = asyncio.run(loop.arun(user_input="test query"))
        
        # Should complete normally without an error
        assert result.status != ExecutionStatus.FAILED
        assert loop._aexecute_steps.call_count == 1
